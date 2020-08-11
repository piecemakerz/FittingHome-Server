#!/usr/bin/python
#! -*- encoding: utf-8 -*-

import os
import subprocess
from subprocess import call
import sys


# CHANGE THE FOLLOWING PATHS TO SUIT YOUR SYSTEM

# Indicate the openMVG and openMVS binary directories
OPENMVG_SFM_BIN = "/root/3DReconstruction/openMVG_Build/Linux-x86_64-RELEASE/"
OPENMVS_BIN = "/root/3DReconstruction/openMVS_build/bin/"
# Indicate the openMVG camera sensor width directory
CAMERA_SENSOR_WIDTH_DIRECTORY = "/root/3DReconstruction/openMVG/src/openMVG/exif/sensor_width_database/"
#EXIFTOOL_DIRECTORY = "/home/piecemaker/Desktop/ExifTool/"

	
DEBUG=False

## HELPERS for terminal colors
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
NO_EFFECT, BOLD, UNDERLINE, BLINK, INVERSE, HIDDEN = (0,1,4,5,7,8)

#from Python cookbook, #475186
def has_colours(stream):
    if not hasattr(stream, "isatty"):
        return False
    if not stream.isatty():
        return False # auto color only on TTYs
    try:
        import curses
        curses.setupterm()
        return curses.tigetnum("colors") > 2
    except:
        # guess false in case of error
        return False
has_colours = has_colours(sys.stdout)

def printout(text, colour=WHITE, background=BLACK, effect=NO_EFFECT):
        if has_colours:
                seq = "\x1b[{};{};{}m".format(effect, 30+colour, 40+background) + text + "\x1b[0m"
                sys.stdout.write(seq+'\r\n')
        else:
                sys.stdout.write(text+'\r\n')

## OBJECTS to store config and data in

def everyImageFileName(directoryPath):
    file_list = os.listdir(directoryPath)
    file_list_jpg = [file for file in file_list if file.endswith(".jpg")]
    return file_list_jpg

class ConfContainer(object):
    """Container for all the config variables"""
    pass

conf=ConfContainer()

class aStep:
    def __init__(self, info, cmd, opt):
        self.info = info
        self.cmd = cmd
        self.opt = opt

class stepsStore :
    def __init__(self):
        self.steps_data=[
            ["Intrinsics analysis",
                os.path.join(OPENMVG_SFM_BIN,
                             "openMVG_main_SfMInit_ImageListing"),
                ["-i", "%input_dir%", "-o", "%matches_dir%", "-d", "%camera_file_params%", "-g", "0"
                 ]],
            ["Compute features",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_ComputeFeatures"),
                ["-i", "%matches_dir%/sfm_data.json", "-o", "%matches_dir%"                # , "-f", "1"
                 , "-p", "ULTRA"
                 #, "-n", "3"
                 , "-m", "AKAZE_FLOAT"
                 ]],
            ["Compute matches",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_ComputeMatches"),
                ["-i", "%matches_dir%/sfm_data.json", "-o", "%matches_dir%", "-n", "ANNL2", "-r", "0.8"
                #, "-v", "30"
                 ]],
            ["Incremental reconstruction",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_IncrementalSfM2"),
                ["-i", "%matches_dir%/sfm_data.json", "-m", "%matches_dir%", "-o", "%reconstruction_dir%"  # , "-M", "%matches_dir%/matches.h.bin"
                 # , "-f", "NONE"
                 , "-S", "STELLAR", "-t", "2"
                 ]],
            ["Export to openMVS",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_openMVG2openMVS"),
                ["-i", "%reconstruction_dir%/sfm_data.bin", "-o", "%mvs_dir%/scene.mvs", "-d", "%mvs_dir%"]],
            ["Densify point cloud",
                os.path.join(OPENMVS_BIN, "DensifyPointCloud"),
                ["--input-file", "%mvs_dir%/scene.mvs", "-w", "%mvs_dir%"
                #, "--resolution-level", "3"
                , "--max-resolution", "640"
                #, "--number-views", "0"
                # , "--filter-point-cloud", "1"
                 ]],
            ["Reconstruct the mesh",
                os.path.join(OPENMVS_BIN, "ReconstructMesh"),
                ["%mvs_dir%/scene_dense.mvs", "-w", "%mvs_dir%", "--remove-spurious", "50"
                #, "--smooth", "1"
                 ]],
            ["Refine the mesh",
                os.path.join(OPENMVS_BIN, "RefineMesh"),
                ["%mvs_dir%/scene_dense_mesh.mvs", "-w", "%mvs_dir%"
                #"--resolution-level", "3"
                #, "--decimate", "0"
                #,"--scales", "1"
                #, "--max-views", "30"
                #, "--max-face-area", "0"
                ]],
            ["Texture the mesh",
                os.path.join(OPENMVS_BIN, "TextureMesh"),
                ["%mvs_dir%/scene_dense_mesh_refine.mvs", "-w", "%mvs_dir%"                 # ["%mvs_dir%/scene_dense_mesh.mvs","-w", "%mvs_dir%"
                 #, "--resolution-level", "3"
                 ]]
        ]

    def __getitem__(self, indice):
        return aStep(*self.steps_data[indice])

    def length(self):
        return len(self.steps_data)

    def apply_conf(self, conf):
        """ replace each %var% per conf.var value in steps data """
        for s in self.steps_data :
            o2=[]
            for o in s[2]:
                co=o.replace("%input_dir%",conf.input_dir)
                co=co.replace("%output_dir%",conf.output_dir)
                co=co.replace("%matches_dir%",conf.matches_dir)
                co=co.replace("%reconstruction_dir%",conf.reconstruction_dir)
                co=co.replace("%mvs_dir%",conf.mvs_dir)
                co=co.replace("%camera_file_params%",conf.camera_file_params)
                o2.append(co)
            s[2]=o2

steps=stepsStore()

## ARGS
import argparse
parser = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description="Photogrammetry reconstruction with these steps : \r\n"+
        "\r\n".join(("\t{}. {}\t {}".format(t, steps[t].info, steps[t].cmd) for t in range(steps.length())))
    )
parser.add_argument('input_dir', help="the directory wich contains the pictures set.")
parser.add_argument('output_dir', help="the directory wich will contain the resulting files.")
parser.add_argument('-f','--first_step', type=int, default=0, help="the first step to process")
parser.add_argument('-l','--last_step', type=int, default=10, help="the last step to process" )

group = parser.add_argument_group('Passthrough',description="Option to be passed to command lines (remove - in front of option names)\r\ne.g. --1 p ULTRA to use the ULTRA preset in openMVG_main_ComputeFeatures")
for n in range(steps.length()) :
    group.add_argument('--'+str(n), nargs='+')

parser.parse_args(namespace=conf) #store args in the ConfContainer

## FOLDERS

def mkdir_ine(dirname):
    """Create the folder if not presents"""
    if not os.path.exists(dirname):
        os.mkdir(dirname)

#Absolute path for input and ouput dirs
conf.input_dir=os.path.abspath(conf.input_dir)
conf.output_dir=os.path.abspath(conf.output_dir)

if not os.path.exists(conf.input_dir):
    sys.exit("{} : path not found".format(conf.input_dir))


conf.matches_dir = os.path.join(conf.output_dir, "matches")
conf.reconstruction_dir = os.path.join(conf.output_dir, "reconstruction_sequential")
conf.mvs_dir = os.path.join(conf.output_dir, "mvs")
conf.camera_file_params = os.path.join(CAMERA_SENSOR_WIDTH_DIRECTORY, "sensor_width_camera_database.txt")

mkdir_ine(conf.output_dir)
mkdir_ine(conf.matches_dir)
mkdir_ine(conf.reconstruction_dir)
mkdir_ine(conf.mvs_dir)

steps.apply_conf(conf)

## WALK
print("# Using input dir  :  {}".format(conf.input_dir))
print("#       output_dir :  {}".format(conf.output_dir))
print("# First step  :  {}".format(conf.first_step))
print("# Last step :  {}".format(conf.last_step))

'''
file_list_jpg = everyImageFileName(conf.input_dir)
for file_jpg in file_list_jpg:
    cmdline = os.path.join(EXIFTOOL_DIRECTORY, "exiftool") + " -TagsFromFile" + " /home/hyukwonlee/Desktop/pictures2/" + file_jpg \
        + " -all:all " + "/home/hyukwonlee/Desktop/openMVG_Material/Images/" + file_jpg
    pStep = subprocess.Popen(cmdline, shell=True)
    pStep.wait()
call('find ' + conf.input_dir + ' -name \'*.jpg_original*\' -delete', shell=True)
'''

for cstep in range(conf.first_step, conf.last_step+1):
    try:
        printout("#{}. {}".format(cstep, steps[cstep].info), effect=INVERSE)
    except IndexError:
        # There are not enough steps in stepsStore.step_data to get to last_step
        break

    opt=getattr(conf,str(cstep))
    if opt is not None :
        #add - sign to short options and -- to long ones
        for o in range(0,len(opt),2):
            if len(opt[o])>1:
                opt[o]='-'+opt[o]
            opt[o]='-'+opt[o]
    else:
        opt=[]

    #Remove steps[cstep].opt options now defined in opt
    for anOpt in steps[cstep].opt :
        if anOpt in opt :
            idx=steps[cstep].opt.index(anOpt)
            if DEBUG :
                print('#\t'+'Remove '+ str(anOpt) + ' from defaults options at id ' + str(idx))
            del steps[cstep].opt[idx:idx+2]

    cmdline = [steps[cstep].cmd] + steps[cstep].opt + opt

    if not DEBUG :
        print(cmdline)
        pStep = subprocess.Popen(cmdline)
        pStep.wait()
    else:
        print('\t'+' '.join(cmdline))
