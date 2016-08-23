'''
    Copyright (c) 2016 Timothy Savannah

    All Rights Reserved, Licensed under LGPL version 3.0

    See LICENSE with distribution for details.


    Some compat stuff to work with multiple python versions
'''
import sys

# vim: set ts=4 sw=4 st=4 expandtab :

##########################################################################
#### strify -
##
##    In python 3, redis returns "bytes", so convert to str in that case.
##        In python 3, will convert bytes -> str.
##        If passed a list/tuple, will recurse and convert any contained
#           bytes -> str.
#
#         In python 2, is a no-op and returns the same object.
#
##########################################################################
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

#################################

# vim: set ts=4 sw=4 st=4 expandtab :
    

