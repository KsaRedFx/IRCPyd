from __future__ import print_function

try:
    import asyncio
    from IRCPydCore import core34 as core
    print("Using Py3")
except ImportError:
    from IRCPydCore import core27 as core
    print("Using Py2")
core.run()