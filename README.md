# SafeRedisLock
Python library for locks across processes/servers which is safe and implements expiration/global timeout

A RedisLock implementation that supports a global timeout (automatically releases after a given period), which can be refreshed.
This prevents a crashed process from hosing the lock forever, or unsafe semantics to otherwise clear or manage against such an issue.

Also checks Redis each time to see if lock is held (or called hasLock method), instead of relying on an internal pointer.

SafeRedisLock Class
-------------------

**\_\_init\_\_**

	def __init__(self, key, globalTimeout=0.0)
		'''
			Create a SafeRedisLock.

			@param key <str> - A key which will identify this lock.
			@param globalTimeout <float> - If 0, this is an unsafe lock. Otherwise, the lock will automatically expire after this many seconds. The lock timer can be refreshed by calling "acquire" again when one holds the lock. Set this to a reasonable value to prevent application crashes etc from hosing the lock forever.
		'''

**acquire**

	def acquire(self, blocking=True, blockingTimeout=0.0):
		'''
			acquire - Attempt to acquire the lock.

			@param blocking <bool> - If True, wait until we obtain the lock before returning. Otherwise, we will return right away with True or False on whether we obtained the lock.
			@param blockingTimeout <float> - If blocking is True, will wait up to this many seconds to obtain the lock, otherwise give-up and return False.

			Calling this function when you already hold the lock on the calling object will refresh its timer, i.e. you will then have #globalTimeout seconds to release before automatically being released.

			@return <bool> - Returns True if we got the lock (or refreshed it), otherwise False.
		'''

**release**

	def release(self):
		'''
			release - Release the lock if held.

			@return <bool> - True if we released it, False if we didn't actually have it.
		'''

**hasLock** *(property)*

	@property
	def hasLock(self):
		'''
			hasLock - Property. Checks Redis to see if we are currently holding the lock with this object.
		'''

**clear**

	def clear(self):
		'''
			clear - DELETE THE LOCK. THIS AFFECTS ALL USERS EVERYWHERE, AND CLEARS THE CURRENT LOCK QUEUE.

			If a lock is currently sitting in acquire, it should put itself back in the queue. Use this method only if you know what you're doing...
		'''
