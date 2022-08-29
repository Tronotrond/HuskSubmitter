# HuskSubmitter
Husk USD Standalone Plugin and Submitter for Thinkbox Deadline.

# About
For submitting .usd scene files to Thinkbox Deadline, using the Husk Standalone renderer. 

Thinkbox Deadline Path Remapping (i.e. changing paths between linux and windows nodes) doesn't work
for paths set inside the .usd file. 

This plugin was developed to extract the metadata and rendersettings from .usd file so Deadline
can do the re-mapping needed and also that these settings can changed and overwritten at submission 
or via the Job Properties without having to re-export and re-submit the .usd scene file. 
It depends on the Pixar's Universal Scene Description library usd-core Python API, and this needs
to be added to the Python Search Path with your Deadline Repository Options. 

To keep everything close to Deadline Standards, the submitter GUI and settings are based off the 
Redshift Standalone submitter shipped with Deadline. 

# Requirements:
- Python, developed and tested with Python 3.7.
	- Currently doesn't seem to work with Python greater than Python 3.8
- usd-core Python API: https://pypi.org/project/usd-core/
- Thinkbox Deadline, PY3 version: https://www.awsthinkbox.com/
- Python and libraries needs to be installed on any computer you submit from.

# Installation
- Add usd-core library path to Python Search Path in Deadline resposity options 
- Copy folders with files into <Deadline Repository>/custom directory

# FAQ
- Deadline Shows a PXR related module error:
	- I've seen errors happening on version 10.1.19.x. Upgrading to Deadline 10.1.20 or never with Python3 seems to work. Also make sure Python Sandbox version is set to 3 in the repository options

# To-do:
- Implement saving and exposing as many render settings as possible to Deadline.
	- Change between Karma XPU/CPU 
	- Change Path Tracing or Pixel Samples 
	- Change Limits 
- Houdini Submitter ROP 
	- Option to export .usd scene on submission
	- Option to submit .usd export job to farm and render job as a dependent job.
	- Options for separate groups and settings for .usd export and render job. 

