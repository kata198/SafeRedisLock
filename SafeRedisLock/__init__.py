'''
    Copyright (c) 2016 Timothy Savannah

    All Rights Reserved, Licensed under LGPL version 3.0

    See LICENSE with distribution for details.
'''

import redis
import time
import uuid


class SafeRedisLock(object):
    '''
        SafeRedisLock - A RedisLock implementation that supports a global timeout, which can be refreshed. This prevents a crashed process from hosing the lock forever, or unsafe semantics to otherwise clear or manage against such an issue.

        Also checks Redis each time to see if lock is held (or called hasLock method), instead of relying on an internal pointer.
    '''
    POLL_INTERVAL = .02

    def __init__(self, key, globalTimeout=0.0):
        '''
            Create a SafeRedisLock.

            @param key <str> - A key which will identify this lock.
            @param globalTimeout <float> - If 0, this is an unsafe lock. Otherwise, the lock will automatically expire after this many seconds. The lock timer can be refreshed by calling "acquire" again when one holds the lock. Set this to a reasonable value to prevent application crashes etc from hosing the lock forever.
        '''
        
        self.key = key
        self.globalTimeout = globalTimeout
        # Double your random, double your fun...
        self.uuid = str(uuid.uuid4()) + str(uuid.uuid4())
        self.conn = redis.Redis()

        self.acquiredAt = None

    
    def acquire(self, blocking=True, blockingTimeout=0.0):
        '''
            acquire - Attempt to acquire the lock.

            @param blocking <bool> - If True, wait until we obtain the lock before returning. Otherwise, we will return right away with True or False on whether we obtained the lock.
            @param blockingTimeout <float> - If blocking is True, will wait up to this many seconds to obtain the lock, otherwise give-up and return False.

            Calling this function when you already hold the lock on the calling object will refresh its timer, i.e. you will then have #globalTimeout seconds to release before automatically being released.

            @return <bool> - Returns True if we got the lock (or refreshed it), otherwise False.
        '''
        if self.hasLock is True:
            # Refresh the lock
            now = time.time()
            nextInLine = self.conn.lrange(self.key, -1, -1)
            if not nextInLine:
                # Cleared.
                return False
            oldKey = nextInLine[0]
            (ownerUuid, ownerTimestamp) = oldKey.split('__')
            if ownerUuid != self.uuid:
                # We got bumped.
                return False
            
            timestampedKey = "%s__%f" %(self.uuid, time.time())
            pipeline = self.conn.pipeline()
            self.conn.linsert(self.key, 'AFTER', oldKey, timestampedKey)
            self.conn.lrem(self.key, oldKey)

            return True

        self._genUuid()
        
        start = now = time.time()

        timestampedKey = "%s__%f" %(self.uuid, now)

        self.conn.lpush(self.key, timestampedKey)


        if blockingTimeout:
            keepGoing = lambda : time.time() - start < blockingTimeout
        else:
            keepGoing = lambda : True

        while keepGoing():
            nextInLine = self.conn.lrange(self.key, -1, -1)
            if not nextInLine:
                # Something happened, just incase remove ourself and repush
                self.conn.lrem(self.key, timestampedKey)
                self.conn.lpush(self.key, timestampedKey)
                nextInLine = self.conn.lrange(self.key, -1, -1)
                if not nextInLine:
                    try:
                        self.conn.lrem(self.key, timestampedKey)
                    except:
                        pass
                    raise Exception('Redis is not behaving.')
            nextInLine = nextInLine[0]

            if nextInLine == timestampedKey:
                self._setGotLock()
                return True

            if self.globalTimeout:
                now = time.time()
                (ownerUuid, ownerTimestamp) = nextInLine.split('__')
                ownerTimestamp = float(ownerTimestamp)
                if now - ownerTimestamp > self.globalTimeout:
                    # The next key in line is past the global key timeout
                    allKeys = self.conn.lrange(self.key, 0, -1)
                    allKeys.reverse()
                    if timestampedKey not in allKeys:
                        # Something happened and key got cleared, put us back in.
                        self.conn.lpush(self.key, timestampedKey)
                        continue


                    i = 0
                    for key in allKeys:
                        (nextUuid, nextTimestamp) = key.split('__')
                        nextTimestamp = float(nextTimestamp)
                        if key == timestampedKey:
                            # We are next non-expired key, our job is to cleanup.
                            for j in range(i):
                                self.conn.lrem(self.key, allKeys[j])
                            # We are now the next key and have the lock.
                            self._setGotLock()
                            return True

                        # There are still locks ahead of us which are not expired. 
                        # They will go first and cleanup the list.
                        if now - nextTimestamp < self.globalTimeout:
                            break
                        i += 1

            if blocking is False:
                # Not blocking and we didn't key the lock
                self.conn.lrem(self.key, timestampedKey)
                return False

            time.sleep(self.POLL_INTERVAL)

        self.conn.lrem(self.key, timestampedKey)
        return False

    def release(self):
        '''
            release - Release the lock if held.

            @return <bool> - True if we released it, False if we didn't actually have it.
        '''
        if not self.hasLock:
            return False

        i = 0
        ret = False
        lineItems = self.conn.lrange(self.key, 0, -1)
        lineItems.reverse()
        pipeline = self.conn.pipeline()
        for item in lineItems:
            if item.split('__')[0] == self.uuid:
                pipeline.lrem(self.key, item)
                if i == 0:
                    # We had the lock
                    ret = True
        pipeline.execute()

        # self.hasLock = False
        return ret

        
    @property
    def hasLock(self):
        '''
            hasLock - Property. Checks Redis to see if we are currently holding the lock with this object.
        '''
        nextInLine = self.conn.lrange(self.key, -1, -1)
        if not nextInLine:
            return False

        nextInLine = nextInLine[0]
        (ownerUuid, ownerTimestamp) = nextInLine.split('__')
        if ownerUuid == self.uuid:
            if not self.globalTimeout:
                return True
            if time.time() - float(ownerTimestamp) < self.globalTimeout:
                return True
            else:
                return False
        return False
            

    def clear(self):
        '''
            clear - DELETE THE LOCK. THIS AFFECTS ALL USERS EVERYWHERE, AND CLEARS THE CURRENT LOCK QUEUE.

            If a lock is currently sitting in acquire, it should put itself back in the queue. Use this method only if you know what you're doing...
        '''
        self.conn.delete(self.key)

    def _setGotLock(self):
        #self.hasLock = True
        self.acquiredAt = time.time()

    def _genUuid(self):
        self.uuid = str(uuid.uuid4()) + str(uuid.uuid4())
