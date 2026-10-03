"""Names that only other libraries use, so that the dead-code check counts them as used.

The check cannot see a library read an attribute, or call a method, that our code only sets or
defines. Each line names one, with what uses it. `_` stands for any object, as the check's
allow-list format has it.
"""

# ruff: noqa: B018, F821

_.flush  # the ZIP library flushes the buffer the archive is written to
_.compress_type  # set on a ZIP entry, for the ZIP library to read
_.file_size  # set on a ZIP entry, for the ZIP library to read
_.handlers  # set on the web server's loggers, for the logging module to read
event_id  # carried by every domain event, for whatever handles or stores it
timestamp  # carried by every domain event, for whatever handles or stores it
