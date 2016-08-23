'''
    Copyright (c) 2016 Timothy Savannah

    All Rights Reserved, Licensed under LGPL version 3.0

    See LICENSE with distribution for details.
'''

import redis
import time
import uuid
import socket
import sys

DEFAULT_POLL_INTERVAL = .02
DEFAULT_GLOBAL_TIMEOUT = 30.0

__version__ = '1.0.0'
__version_tuple__ = (1, 0, 0)

__all__ = ('DEFAULT_POLL_INTERVAL', 'SafeRedisLock')

# Calculate this ONCE so that if the hostname changes it doesn't screw with the lock
MY_HOSTNAME = socket.gethostname()

# In python 3, redis returns "bytes", so convert to str in that case.
if sys.version_info.major >= 3:
    def strify(x):
        # If we have "bytes", turn it into a string.
        if isinstance(x, bytes):
            return x.decode('utf-8')
        # If we have a list (like from lrange), convert each item to a string.
        elif isinstance(x, (tuple, list)):
            ret = [strify(item) for item in x]
            if isinstance(ret, tuple):
                ret = tuple(ret)
            return ret
        # Otherwise, return what we got.
        return x
else:
    # Python 2 we already have what we want
    strify = lambda x : x

class SafeRedisLock(object):
    '''
        SafeRedisLock - An atomic shared lock implementation using Redis which is implemented as a queue (so multiple folks trying to acquire get the lock in-turn), and supports a global timeout (A set timer, which can be refreshed by a lock-holder, which marks the maximum time before the lock automatically expires). This timeout prevents a crashed process from holding the lock forever, or unsafe semantics to otherwise clear or manage against such an issue.

        SafeRedisLock also checks the Redis server each time "hasLock" property is checked, instead of using a local pointer like some other implementations, to ensure a valid shared-state across all clients.

        *Properties of interest*:

            acquiredAt <float/None> - This property reflects the timestamp wherein we acquired the lock, or "None" if we have never acquired a lock on this object. If we release the lock, or we are automatically expired, or some client calls "clear", this value will remain the timestamp of the LAST lock held.

            lockTimestamp <float/None> - This property reflects the current timestamp on this lock. This differs from #acquiredAt in that calling "acquire" whilst holding the lock will refresh the lock's timestamp, and this value will be updated. If we release the lock, or we are automatically expired, or some client calls "clear", this value will remain the timestamp of the LAST lock held.

            hasLock    <bool> - Perform a query of the Redis server to determine if we still hold the lock

            secondsRemaining <float/None> - The number of seconds remaining before this lock is automatically expired. If we have never acquired a lock, this will be "None". This number could be negative if we have passed the global timeout since expiring.

        *Methods of interest*:

            acquire - Attempt to acquire this lock. If called when we already have the lock, this will refresh our timestamp (So we then have a full #globalTimeout seconds left before automatically being released )

            release - Release the lock

            clear   - Forcibly clear the lock queue for everyone. You should not call this method in normal usage of SafeRedisLock.

        @See __init__ method docstring for more information

    '''
    def __init__(self, key, globalTimeout=DEFAULT_GLOBAL_TIMEOUT, pollInterval=DEFAULT_POLL_INTERVAL, redisConnectionParams={}):
        '''
            Create a SafeRedisLock.

            @param key <str> - A key which will identify this lock. (e.x. "MyItemLock")

            @param globalTimeout <float> - The maximum number of seconds that a lock can be held without refreshing (lock holder calls "acquire" again whilst still holding the lock).
               This defaults to DEFAULT_GLOBAL_TIMEOUT (30.0 seconds).
               Set this to a reasonable value for your application. A value of 0 is an unsafe lock, that is it will never automatically expire. If an application crashes or never releases the lock acquired and globalTimeout is 0, the lock will be stuck forever (or until some client calls "clear"). You most likely do not want this behaviour, so pick a good value. Generally 4 times the expected duration that a lock will be held is a good value, and a design such that the lock-holder refreshes (calls acquire whilst holding lock) for larger-than-normal lock-holding tasks.

            @param pollInterval <float> - Minimum number of seconds between polling the Redis server for lock status. Defaults to DEFAULT_POLL_INTERVAL (0.02 seconds)

            @param redisConnectionParams <dict> - Parameters required to establish a Redis connection (passed to redis.Redis.__init__). See help(redis.Redis.__init__) for details.
                Generally, the keys you may use are "host" [hostname of Redis server], "port" [port on which to connect], and "db" [A number representing the Redis namespace in which to store the key]




        '''

        # self.key - The key for this lock
        self.key = key
        # self.globalTimeout - Automatic expiration of locks after this much time
        self.globalTimeout = globalTimeout
        # self.uuid
        self.uuid = self._genUuid()

        if pollInterval <= 0:
            raise ValueError('Provided poll interval %s must be > 0 seconds.' %(repr(pollInterval), ))
        # self.pollInterval - Minimum number of seconds between polling the Redis server waiting for lock (in acquire method)
        self.pollInterval = pollInterval
        # self.redisConnectionParams - Dict of paramaters to pass to redis.Redis when creating a connection.
        self.redisConnectionParams = redisConnectionParams

        # self.acquiredAt - A timestamp representing the last time we acquired the lock.
        self.acquiredAt = None

        # self.lockTimestamp - The timestamp we have marked on the current lock. 
        #  This will be updated when acquire() is called while the lock is held, whereas #acquiredAt will not.
        self.lockTimestamp = None
    
    def acquire(self, blocking=True, blockingTimeout=0.0):
        '''
            acquire - Attempt to acquire the lock.

            @param blocking <bool> - If True, wait until we obtain the lock before returning. Otherwise, we will return right away with True or False on whether we obtained the lock.
            @param blockingTimeout <float> - If blocking is True, will wait up to this many seconds to obtain the lock, otherwise give-up and return False.

            Calling this function when you already hold the lock on the calling object will refresh its timer, i.e. you will then have #globalTimeout seconds to release before automatically being released.

            @return <bool> - Returns True if we got the lock (or refreshed it), otherwise False.
        '''
        conn = self._getConnection()
        key = self.key

        if self.hasLock is True:
            # Refresh the lock
            now = time.time()
            nextInLine = strify(conn.lrange(key, -1, -1))
            if not nextInLine:
                # Cleared.
                return False
            oldKey = nextInLine[0]
            (ownerUuid, ownerTimestamp) = oldKey.split('__')
            if ownerUuid != self.uuid:
                # We got bumped.
                return False

            # We still hold the lock, so refresh it
            self.__updateLockTimestamp(oldKey, conn)

            return True

        # Generate a new uuid for a new lock request
        self.uuid = self._genUuid()
        pollInterval = self.pollInterval
        
        start = now = time.time()

        timestampedKey = "%s__%f" %(self.uuid, now)

        conn.lpush(key, timestampedKey)


        if blockingTimeout:
            keepGoing = lambda : time.time() - start < blockingTimeout
        else:
            keepGoing = lambda : True

        while keepGoing():
            nextInLine = strify(conn.lrange(key, -1, -1))
            if not nextInLine:
                # Something happened, just incase remove ourself and repush
                conn.lrem(key, timestampedKey)
                conn.lpush(key, timestampedKey)
                nextInLine = strify(conn.lrange(key, -1, -1))
                if not nextInLine:
                    try:
                        conn.lrem(key, timestampedKey)
                    except:
                        pass
                    raise Exception('Redis is not behaving.')
            nextInLine = nextInLine[0]

            if nextInLine == timestampedKey:
                # We are the next in line and have the lock!

                self._setGotLock()
                # Update our timestamp to match that we just got the lock.
                self.__updateLockTimestamp(timestampedKey, conn)
                return True

            if self.globalTimeout:
                now = time.time()
                (ownerUuid, ownerTimestamp) = nextInLine.split('__')
                ownerTimestamp = float(ownerTimestamp)
                if now - ownerTimestamp > self.globalTimeout:
                    # The next key in line is past the global key timeout
                    allKeys = strify(conn.lrange(key, 0, -1))
                    allKeys.reverse()
                    if timestampedKey not in allKeys:
                        # Something happened and key got cleared, put us back in.
                        conn.lpush(key, timestampedKey)
                        continue


                    for i in range(len(allKeys)):
                        curKey = allKeys[i]

                        (nextUuid, nextTimestamp) = curKey.split('__')
                        nextTimestamp = float(nextTimestamp)
                        if curKey == timestampedKey:
                            # We are next non-expired key, our job is to cleanup.
                            for j in range(i):
                                conn.lrem(key, allKeys[j])
                            # We are now the next key and have the lock.
                            self._setGotLock()
                            self.__updateLockTimestamp(timestampedKey, conn)
                            return True

                        # There are still locks ahead of us which are not expired. 
                        # They will go first and cleanup the list.
                        if now - nextTimestamp < self.globalTimeout:
                            break

            if blocking is False:
                # Not blocking and we didn't key the lock
                conn.lrem(key, timestampedKey)
                return False

            time.sleep(pollInterval)

        conn.lrem(key, timestampedKey)
        return False

    def release(self):
        '''
            release - Release the lock if held.

            @return <bool> - True if we released it, False if we didn't actually have it.
        '''
        if not self.hasLock:
            return False

        conn = self._getConnection()

        i = 0
        ret = False
        lineItems = strify(conn.lrange(self.key, 0, -1))
        lineItems.reverse()
        pipeline = conn.pipeline()
        for item in lineItems:
            if item.split('__')[0] == self.uuid:
                pipeline.lrem(self.key, item)
                if i == 0:
                    # We had the lock
                    ret = True
        pipeline.execute()

        self.lockTimestamp = None

        # self.hasLock = False
        return ret

    @property
    def hasLock(self):
        '''
            hasLock - Property. Checks Redis to see if we are currently holding the lock with this object.
                This will query the server, so if you plan to call this often (like in a series of conditionals), consider calling once and assigning to a local variable.
        '''
        conn = self._getConnection()

        nextInLine = strify(conn.lrange(self.key, -1, -1))
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
            

    @property
    def secondsRemaining(self):
        try:
            return self.lockTimestamp - (time.time() - self.globalTimeout)
        except:
            return None

    def clear(self):
        '''
            clear - DELETE THE LOCK. THIS AFFECTS ALL USERS EVERYWHERE, AND CLEARS THE CURRENT LOCK QUEUE.

            If a lock is currently sitting in acquire, it should put itself back in the queue. Use this method only if you know what you're doing...
        '''
        conn = self._getConnection()
        conn.delete(self.key)

        self.acquiredAt = self.lockTimestamp = None


    def __updateLockTimestamp(self, oldKey, conn=None):
        '''
            __updateLockTimestamp - Private method to refresh the timestamp on our key.
              This is a PRIVATE method - It does not check that we have the key, etc.
              Call "acquire" a whilst holding the lock if you want to refresh your keys timestamp.
        '''
        # We still hold the lock, so refresh it
        conn = conn or self._getConnection()

        self.lockTimestamp = time.time()
        timestampedKey = "%s__%f" %(self.uuid, self.lockTimestamp)
        pipeline = conn.pipeline()
        pipeline.linsert(self.key, 'AFTER', oldKey, timestampedKey)
        pipeline.lrem(self.key, oldKey)
        pipeline.execute()

    def _setGotLock(self):
        '''
            _setGotLock - Set properties relating to acquiring a lock
        '''
        #self.hasLock = True
        self.acquiredAt = time.time()
        self.lockTimestamp = self.acquiredAt

    def _genUuid(self):
        '''
            _genUuid - Generate the uuid for this instance's lock acquisition.
                This will be called each time we enter the queue to acquire a lock.

                This implementation uses the hostname and 2 appended uuid4's

            @return <str> - A unique ID
        '''
        # Double your random, double your fun...
        return "%s+%s%s" %(MY_HOSTNAME, str(uuid.uuid4()), str(uuid.uuid4()))

    def _getConnection(self):
        '''
            _getConnection - Get a Redis connection based on the connection params provided in __init__
        '''
        return redis.Redis(**self.redisConnectionParams)


    @property
    def _sq(self):
        '''
            _sq - Debug method to view the queue. Note that this goes right-to-left.
        '''
        return strify(self._getConnection().lrange(self.key, 0, -1))
