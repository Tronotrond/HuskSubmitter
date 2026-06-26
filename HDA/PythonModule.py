import hou
import sys
import traceback
import os
import re
import tempfile
import json
import copy
from pprint import pprint

try:
    from CallDeadlineCommand import CallDeadlineCommand
    #from Deadline.Scripting import RepositoryUtils, FrameUtils, ClientUtils, PathUtils
except:
    pass

def InitHDA(kwargs):
    try:
        import PrismInit
    except ImportError:
        print('Prism import error')
        return
    
    #node = hou.pwd()
    node = kwargs['node']
        
    core = PrismInit.pcore
    prj_path = core.projectPath
    filename = core.getCurrentFileName()
    entity = core.getScenefileData(filename)
    
    if not 'type' in entity:
        print('Prism not set up for this scene.\n Husk submitter might not work as intended')
        node.parm('output_type').set(1)
        return
    
    prism_type = entity['type']
    vers = entity['version']
    seq = entity['sequence']
    shot = entity['shot']
    
    #For now, lets just return if this is not a shot
    if prism_type != 'shot':
        return

    ident = str(seq) + '_' + str(shot)

    node.setParms({'identifier': ident}) 
    
    identifier = node.evalParm('identifier') 
    aov_ident = node.evalParm('aov_ident') 
    
    out_img = PrismOutput(prj_path, entity, identifier, aov_ident)
    node.setParms({'out': out_img}) 

    
    
def split_file_path_and_format(filename):
    # Split the path into directory and file name
    directory, file_name = os.path.split(filename)

    # Define a function to replace the padding
    def replace_padding(match):
        padding_type = match.group(0)  # Get the matched padding token
        if padding_type == "$F":
            return "#"
        elif padding_type == "$F2":
            return "##"
        elif padding_type == "$F3":
            return "###"
        elif padding_type == "$F4":
            return "####"
        else:
            return padding_type  # Return the original token if no match

    # Replace padding in the filename using regex
    formatted_file_name = re.sub(r'\$F[0-9]*', replace_padding, file_name)

    return directory, formatted_file_name
   

def ExportUSD():
    node = hou.pwd()
    
    # update output path just in case
    OutputChanged()
    supress_popups = node.evalParm('supress_popup')
    always_overwrite = node.evalParm('always_overwrite')
    
    usd_rop = node.node('usd_rop')
    usd_file_path = usd_rop.parm('lopoutput').eval()
    
    #Check basic render settings
    rnd_result = CheckRenderSettings()
    if rnd_result == None:
        return
    if rnd_result['camera'] == None:
        if not supress_popups:
            if hou.ui.displayMessage('Render settings Camera not found!\nDo you want to continue?', buttons=("OK","Cancel"), title="Warning") == 1:
                return
        else:
            print('Render settings Camera not found. Cancelling...')
            return
               
    #Check if file already exists
    if os.path.isfile(usd_file_path):
        if always_overwrite:
            pass
        elif hou.ui.displayMessage("USD file already exists.\nOverwrite file?", buttons=("OK","Cancel"), title="Warning") == 1:
            return False
            
    
    #Click export button on USD ROP
    usd_rop.parm('execute').pressButton()
    
    #Check that file was created
    if os.path.isfile(usd_file_path):
        return True       
        
    return False

        
def CheckRenderSettings():
    # Access the render settings node 
    node = hou.pwd()
    stage = node.stage()
    
    # Iterate over all prims in the stage to find a RenderSettings primitive
    settings_prim = None
    for prim in stage.Traverse():
        if prim.GetTypeName() == "RenderSettings":
            settings_prim = prim
            break  # Stop at the first found RenderSettings prim
    
    #Cancel if no render settings are found
    if settings_prim is None or not settings_prim.IsValid():
        hou.ui.displayMessage("No render settings found on stage..", buttons=("OK",), title="Critical")
        return None
    
    result = {}
    
    resolution = stage.GetPropertyAtPath(f"{settings_prim.GetPath()}.resolution").Get(1)     
    result['resolution'] = resolution
    
    ls = hou.LopSelectionRule()
    ls.setPathPattern('%rendercamera:/Render/rendersettings')
    resolved_paths = ls.expandedPaths(node.inputs()[0])
    if resolved_paths[0]:
        # Get the camera path
        if stage.GetPrimAtPath(resolved_paths[0]):
            #print(f"Camera '{resolved_paths[0]}' exists.")
            result['camera'] = resolved_paths[0]
        else:
            #print(f"Camera '{resolved_paths[0]}' does not exist.")
            result['camera'] = None
            
    return result
    
    
def write_info_file(path, info):
    """Write a Deadline job/plugin info dict to a KEY=VALUE text file."""
    with open(path, 'w') as f:
        for key, value in info.items():
            f.write(f"{key}={value}\n")


def parse_job_id(submit_output):
    """Extract the JobID from a SubmitJob output blob.

    CallDeadlineCommand returns the full multi-line submission report
    (Submitting to Repository.../Result=Success/JobID=.../...), so the bare
    return value must not be used directly as a job id or dependency.

    Deadline job IDs are 24-char hex (Mongo ObjectId). We match that shape
    directly so we never capture a stray fragment of the report.
    """
    text = str(submit_output)

    # Preferred: a JobID= line carrying a valid 24-char hex id.
    match = re.search(r'JobID[=:]\s*([0-9a-fA-F]{24})', text)
    if match:
        return match.group(1)

    # Fallback: any bare 24-char hex token in the output.
    match = re.search(r'\b([0-9a-fA-F]{24})\b', text)
    if match:
        return match.group(1)

    # Nothing usable - surface the raw output so the failure is diagnosable.
    print('parse_job_id: could not find a JobID in submission output:\n' + text)
    return ''


def frame_range_to_string(param):
    # Extract the 'start', 'end', and 'increment' values from the Houdini parameter
    start_frame = param[0]
    end_frame = param[1]
    increment = max(1, param[2])

    # Check if all parameters are integers
    if not (isinstance(start_frame, int) and isinstance(end_frame, int) and isinstance(increment, int)):
        raise ValueError("All parameters must be integers.")

    # Ensure increment is not zero to avoid division by zero
    if increment == 0:
        raise ValueError("Increment cannot be zero.")

    # If increment is 1, return a simple range
    if increment == 1:
        return f"{start_frame}-{end_frame}"
    else:
        # Generate a string that shows the frame range divided by increment
        frames = [str(frame) for frame in range(start_frame, end_frame + 1, increment)]
        return ', '.join(frames)
        
def UpdateGroupFromRenderDelegate():
    node = hou.pwd()
    subInfo = json.loads( hou.getenv( "Deadline_Submission_Info" ) )

    groups = subInfo[ "Groups" ]
    
    # Auto update groups and limits
    delegate_parm = node.parm('delegate')
    
    #Workaround due to this parm sometimes returning Nonetype
    if delegate_parm == None:
        return
        
        
    delegate = delegate_parm.eval()
    
    if delegate == 0 and 'houdini_cpu' in groups:
        node.parm('dl_group').set('houdini_cpu')
        node.parm('dl_limits').set('karma')
    elif delegate == 1 and 'houdini_xpu' in groups:
        node.parm('dl_group').set('houdini_xpu')
        node.parm('dl_limits').set('karma')
    elif delegate == 2 and 'houdini_xpu' in groups:
        node.parm('dl_group').set('houdini_xpu')
        node.parm('dl_limits').set('redshift')
 

def HuskSubmission():
    if not "CallDeadlineCommand" in sys.modules:
        return
    node = hou.pwd()
    
    rnd_result = CheckRenderSettings()
    if rnd_result == None:
        return
        
    supress_popups = node.evalParm('supress_popup')

    #print(rnd_result['resolution'])
    
    # Check if export first toggle is on
    if node.parm('export_first').eval():
        if ExportUSD() == False:
            if not supress_popups:
                hou.ui.displayMessage('USD export failed..', buttons=('OK',), title='Warning')
            else:
                print('USD export failed..')
            return
    else:
        OutputChanged()
    
    #Access the USD ROP
    usd_rop = node.node('usd_rop')
    usd_file_path = usd_rop.parm('lopoutput').eval()
    
    if not os.path.isfile(usd_file_path):
        if not supress_popups:
            hou.ui.displayMessage('USD file not found, please export file first', buttons=('OK',), title='Warning')
        else:
            print('USD file not found, please export file first')
        return
    
    #Grab the unevalated output path -- retaining $F4 etc..
    output_file = node.parm('out').unexpandedString()
    if output_file == '':
        if not supress_popups:
            hou.ui.displayMessage('Output path not set', buttons=('OK',), title='Warning')
        else:
            print('Output path not set')
        return
    
    #Check for empty fields
    identifier = node.parm('identifier').eval()
    aov_ident = node.parm('aov_ident').eval()
    if identifier == '' or aov_ident == '':
        if not supress_popups:
            hou.ui.displayMessage('Identifier and AOV name cannot be empty', buttons=('OK',), title='Warning')
            return
        else:
            print('Identifier and AOV name cannot be empty')
            return
        
    # Get the path of the current Houdini scene
    hip_file_path = hou.hipFile.path()
    # Save Job Info and Plugin Info to temp files
    temp_dir = tempfile.mkdtemp(prefix='houdini_temp_')
        

    if node.parm('trange').eval() == 0:
        frames = int(hou.frame())
    else:
        f = node.parmTuple('fr').eval()
        frames = frame_range_to_string(f)
    
    job_name = node.parm('dl_job_name').eval()
    
    #Get selected render delegate
    rnd_delegate = node.parm('delegate').eval()
    if rnd_delegate == 0:
        delegate = 'BRAY_HdKarma'
    elif rnd_delegate == 1:
        delegate = 'BRAY_HdKarmaXPU'
    elif rnd_delegate == 2:
        delegate = 'Redshift'
        
    #split output and add padding according to deadline standards
    out_split = split_file_path_and_format(output_file)
        
    job_info = {
        "Plugin": "Husk",
        "Name": job_name,
        "Comment": node.parm('dl_comment').eval(),
        "Department": node.parm('dl_department').eval(),
        "Pool": node.parm('dl_pool').eval(),
        "Group": node.parm('dl_group').eval(),
        "Priority": node.parm('dl_priority').eval(),
        "Frames": frames,
        "ChunkSize": node.parm('dl_chuck_size').eval(),
        "LimitGroups": node.parm('dl_limits').eval(),
        "UserName": os.getlogin(),  # Set username for job
        "OutputDirectory0": out_split[0],
        "OutputFilename0": out_split[1],
    }
    
    plugin_info = {
        'SceneFile': f'"{usd_file_path}"',
        'ImageOutputDirectory': f'"{output_file}"',        
        'Renderer': 'Husk',
        'RenderPass': node.evalParm('renderpass'),
        'OverrideResolution': 0,
        'Width': rnd_result['resolution'][0],
        'Height': rnd_result['resolution'][1], 
        'LogLevel': node.parm('loglevel').eval(),
        'OverrideRenderDelegate': 1,
        'RenderDelegate': delegate,
        'CustomArguments': node.parm('custom_args').eval(),
        'DisableMotionBlur': 0,
    }
    
    # Tile Rendering
    if node.evalParm('enable_tile'):
        tile_mode = node.evalParm('tile_mode')
        tiles_x = node.evalParm('custom_tilesx')
        tiles_y = node.evalParm('custom_tilesy')

        if tile_mode == 0:
            # Auto-tile mode: husk renders all tiles in one process and stitches
            # them itself, so this stays a normal single job. No assembly needed.
            plugin_info['CustomArguments'] += ' --autotile --tile-count {} {}'.format(tiles_x, tiles_y)

        elif tile_mode == 1:
            # Distributed tile mode: one render job whose tasks are tiles, plus a
            # dependent assembly job that stitches them with itilestitch.
            #
            # Distributed tiling is single-frame only. Warn the user and force the
            # job to the current frame if a range is set.
            if node.parm('trange').eval() != 0:
                if not supress_popups:
                    if hou.ui.displayMessage(
                        'Distributed tile rendering supports a single frame only.\n\n'
                        'The job will be submitted for the current frame ({}) instead of '
                        'the frame range.\n\nContinue?'.format(int(hou.frame())),
                        buttons=("OK", "Cancel"), title="Warning") == 1:
                        return
                else:
                    print('Distributed tile rendering is single-frame only. Using current frame {}.'.format(int(hou.frame())))

            render_frame = int(hou.frame())
            total_tiles = tiles_x * tiles_y

            # Resolve the output to a concrete single-frame path (expanding $F4 etc.)
            # so itilestitch and husk agree on a real filename rather than a token.
            frame_output = node.parm('out').evalAtFrame(render_frame).replace('\\', '/')
            frame_split = os.path.split(frame_output)

            tile_suffix = '_tile%d'

            # --- Render job: one task per tile ---
            tile_job_info = job_info.copy()
            tile_job_info["Name"] = f"{job_name} [TILES] frame {render_frame}"
            tile_job_info["BatchName"] = f"{job_name} [TILES]"
            # Repurpose the frame range to enumerate tiles: task N renders tile N.
            tile_job_info["Frames"] = f"0-{total_tiles - 1}"
            tile_job_info["ChunkSize"] = 1
            tile_job_info["OutputDirectory0"] = frame_split[0]
            tile_job_info["OutputFilename0"] = frame_split[1]

            tile_plugin_info = copy.deepcopy(plugin_info)
            tile_plugin_info['ImageOutputDirectory'] = frame_output
            tile_plugin_info['TileRendering'] = 1
            tile_plugin_info['TilesX'] = tiles_x
            tile_plugin_info['TilesY'] = tiles_y
            tile_plugin_info['TileSuffix'] = tile_suffix
            tile_plugin_info['RenderFrame'] = render_frame

            tile_job_info_file = os.path.join(temp_dir, f"{job_name}_tiles_info.txt")
            tile_plugin_info_file = os.path.join(temp_dir, f"{job_name}_tiles_plugin.txt")
            write_info_file(tile_job_info_file, tile_job_info)
            write_info_file(tile_plugin_info_file, tile_plugin_info)

            render_job_id = parse_job_id(CallDeadlineCommand(['SubmitJob', tile_job_info_file, tile_plugin_info_file]))
            if not render_job_id:
                msg = 'Tile render job submission failed (no JobID returned). Assembly job not submitted.'
                if not supress_popups:
                    hou.ui.displayMessage(msg, buttons=("OK",), title="Warning")
                else:
                    print(msg)
                return
            print(f"Submitted tile render job ({total_tiles} tiles): {render_job_id}")

            # --- Assembly job: single task, depends on the render job ---
            assembly_job_info = {
                "Plugin": "Husk",
                "Name": f"{job_name} [ASSEMBLY] frame {render_frame}",
                "BatchName": f"{job_name} [TILES]",
                "Comment": "Stitch distributed render tiles",
                "UserName": os.getlogin(),
                "Pool": node.parm('dl_pool').eval(),
                "Group": tile_job_info["Group"],
                "Priority": tile_job_info["Priority"],
                "Frames": "0",
                "ChunkSize": 1,
                "JobDependencies": render_job_id,
                "OutputDirectory0": frame_split[0],
                "OutputFilename0": frame_split[1],
            }
            assembly_plugin_info = {
                "AssemblyJob": 1,
                "ImageOutputDirectory": frame_output,
                "TilesX": tiles_x,
                "TilesY": tiles_y,
                "TileSuffix": tile_suffix,
            }

            assembly_info_file = os.path.join(temp_dir, f"{job_name}_assembly_info.txt")
            assembly_plugin_file = os.path.join(temp_dir, f"{job_name}_assembly_plugin.txt")
            write_info_file(assembly_info_file, assembly_job_info)
            write_info_file(assembly_plugin_file, assembly_plugin_info)

            assembly_job_id = parse_job_id(CallDeadlineCommand(['SubmitJob', assembly_info_file, assembly_plugin_file]))

            # --- Optional cleanup job: remove tile files after assembly ---
            cleanup_job_id = ''
            if node.evalParm('cleanup_tiles'):
                if not assembly_job_id:
                    print('Assembly job id not found; skipping tile cleanup job.')
                else:
                    cleanup_job_info = {
                        "Plugin": "Husk",
                        "Name": f"{job_name} [CLEANUP] frame {render_frame}",
                        "BatchName": f"{job_name} [TILES]",
                        "Comment": "Remove tile images after assembly",
                        "UserName": os.getlogin(),
                        "Pool": node.parm('dl_pool').eval(),
                        "Group": tile_job_info["Group"],
                        "Priority": tile_job_info["Priority"],
                        "Frames": "0",
                        "ChunkSize": 1,
                        "JobDependencies": assembly_job_id,
                        "OutputDirectory0": frame_split[0],
                        "OutputFilename0": frame_split[1],
                    }
                    # Optionally submit the cleanup job suspended so the user can
                    # verify the assembled frame before manually resuming it.
                    if node.evalParm('cleanup_suspended'):
                        cleanup_job_info["InitialStatus"] = "Suspended"
                    cleanup_plugin_info = {
                        "CleanupJob": 1,
                        "ImageOutputDirectory": frame_output,
                        "TilesX": tiles_x,
                        "TilesY": tiles_y,
                        "TileSuffix": tile_suffix,
                    }

                    cleanup_info_file = os.path.join(temp_dir, f"{job_name}_cleanup_info.txt")
                    cleanup_plugin_file = os.path.join(temp_dir, f"{job_name}_cleanup_plugin.txt")
                    write_info_file(cleanup_info_file, cleanup_job_info)
                    write_info_file(cleanup_plugin_file, cleanup_plugin_info)

                    cleanup_job_id = parse_job_id(CallDeadlineCommand(['SubmitJob', cleanup_info_file, cleanup_plugin_file]))

            msg = (f"Tile render submitted.\n\n"
                   f"Render job: {render_job_id}\n"
                   f"Assembly job: {assembly_job_id}")
            if cleanup_job_id:
                msg += f"\nCleanup job: {cleanup_job_id}"
            if not supress_popups:
                hou.ui.displayMessage(msg, buttons=("OK",), title="Notification")
            else:
                print(msg)
            return

    # END TILE RENDERING

    if not os.path.exists(temp_dir):
        try:
            # Create the directory (including any intermediate directories)
            os.makedirs(temp_dir)
            print(f"Directory created: {temp_dir}")
        except Exception as e:
            print(f"Failed to create directory {temp_dir}: {e}")
            return
   
    
    job_info_file = os.path.join(temp_dir, job_name + '_info_file.txt')
    plugin_info_file = os.path.join(temp_dir, job_name + '_plugin_file.txt')
    aux_files = [usd_file_path]
    
    # Write job_info to file
    with open(job_info_file, 'w') as job_file:
        for key, value in job_info.items():
            job_file.write(f"{key}={value}\n")
    
    # Write plugin_info to file
    with open(plugin_info_file, 'w') as plugin_file:
        for key, value in plugin_info.items():
            plugin_file.write(f"{key}={value}\n")
    
    # Submit the job using DeadlineCommand
    deadline_command = CallDeadlineCommand
    submission_args = [job_info_file, plugin_info_file]

    command = ['SubmitJob', submission_args[0], submission_args[1]]
    response = str(CallDeadlineCommand(command))
    if not supress_popups:
        hou.ui.displayMessage(response, buttons=("OK",), title="Notification")
    else:
        print(response)
    
    
def PrismOutput(prj_path, entity, identifier, aov):
    prj_path = prj_path.replace('\\\\', '/')
    prj_path = prj_path.replace('\\', '/')

    if prj_path[-1] == '/':
        prj_path = prj_path[:-1]

    job_name = prj_path.split('/')[-1]
    prism_type = entity['type']
    vers = entity['version']
    seq = entity['sequence']
    shot = entity['shot']
    
    #For now, lets just return if this is not a shot
    if prism_type != 'shot':
        return
    
    #Build Prism specific path
    pre_path = r'03_Production/Shots'     
    post_path = r'Renders/3dRender'
    
    out_path = prj_path + '/' + pre_path + '/' + seq + '/' + shot + '/' + post_path + '/' + identifier + '/' + vers + '/' + aov + '/'
    out_img = out_path + seq + '_' + shot + '_' + vers + '.$F4.exr'
    
    return out_img
    
    
  
    
def RefreshIdentifier():
    try:
        import PrismInit
    except ImportError:
        print('Prism import error')
        return
    
    node = hou.pwd()
        
    core = PrismInit.pcore
    prj_path = core.projectPath
    filename = core.getCurrentFileName()
    entity = core.getScenefileData(filename)
    
    prism_type = entity['type']
    vers = entity['version']
    seq = entity['sequence']
    shot = entity['shot']
    
    #For now, lets just return if this is not a shot
    if prism_type != 'shot':
        return

    ident = str(seq) + '_' + str(shot)
        
    node.parm('identifier').set(ident)
    
    if node.parm('aov_ident').eval() == '':
        node.parm('aov_ident').set('beauty')
        
    
    OutputChanged()

    
def OutputChanged():
    node = hou.pwd()
    prism_available = 0
    
    try:
        import PrismInit
        prism_available = 1
    except ImportError:
        print('Prism libraries not found. Running HDA with limited functionality\n')
        
    parm = node.parm('output_type')
    value = parm.eval()

    
    if value == 0:
        #Prims output path
        if prism_available == 0:
            return
            
        core = PrismInit.pcore
        prj_path = core.projectPath
        filename = core.getCurrentFileName()
        entity = core.getScenefileData(filename)
        
        identifier = node.parm('identifier').eval()
        aov_ident = node.parm('aov_ident').eval()
        
        if identifier == '': 
            identifier = 'render'
            
        if aov_ident == '': 
            aov_ident = 'beauty'
        
        out_img = PrismOutput(prj_path, entity, identifier, aov_ident)
        node.parm('out').set(out_img)
        
        
    elif value == 1:
        None
        #Custom path selection
        #print('custom')

#RefreshIdentifier()

def RenderPassIdentifierAOVSet(kwargs):
    node = kwargs['node']
    passparm = node.parm('renderpass')
    aovparm = node.parm('aov_ident')
    
    passtxt = passparm.eval()
    passtxt = passtxt.split('/')[-1]
    if passtxt != '':
        aovparm.set(passtxt)
    