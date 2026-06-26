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
- usd-core Python API: https://pypi.org/project/usd-core/
- Thinkbox Deadline, PY3 version: https://www.awsthinkbox.com/
- When using the integrated Deadline Submitter, Python and libraries needs to be installed on the computer you submit the job from.
- Using the Houdini Submitter does not have external dependencies beyond the husk plugin being installed on the Deadline Repository.

# Installation
- Add usd-core library path to Python Search Path in Deadline resposity options 
- Copy folders with files into <Deadline Repository>/custom directory

# Houdini HDA
- An example Houdini Submitter HDA + an updated script for the HDA PythonModule is in the HDA folder.
  This is mostly is mostly meant as a starting point to create your own Houdini submitter, if needed.

# FAQ
- Deadline Shows a PXR related module error:
	- I've seen errors happening on version 10.1.19.x. Upgrading to Deadline 10.1.20 or never with Python3 seems to work. Also make sure Python Sandbox version is set to 3 in the repository options

# Tile Rendering (Distributed)
The Houdini HDA submitter supports two tiling modes via the `tile_mode` parameter:

- **Auto-tile (mode 0):** husk renders all tiles in a single process and stitches
  them itself (`--autotile`). Useful for reducing peak memory on one machine. This
  stays a single Deadline job, no assembly needed.
- **Distributed (mode 1):** the image is split into `custom_tilesx` x `custom_tilesy`
  tiles. A single render job is submitted whose *tasks are tiles* (task N renders
  tile N via `--tile-count`/`--tile-index`/`--tile-suffix`), followed by a dependent
  assembly job that stitches the tiles into the final frame with `itilestitch`.

Notes:
- Distributed tiling is **single frame only**. If a frame range is set, the submitter
  warns and falls back to the current frame.
- The assembly job runs under the Husk plugin and resolves `itilestitch` as a sibling
  of the configured husk executable, so it works on a mixed Windows/Linux farm and
  respects Deadline path mapping. No separate executable configuration is required.
- If the `cleanup_tiles` parameter is enabled, a third job (dependent on the assembly
  job) removes the per-tile image files once stitching has completed. It deletes the
  known tile files directly in Python, so it is OS-agnostic across a mixed farm.

# To-do:
- Implement saving and exposing as many render settings as possible to Deadline.
	- Change between Karma XPU/CPU 
	- Change Path Tracing or Pixel Samples 
	- Change Limits 
- Distributed tile rendering across a frame *range* (currently single-frame only).


