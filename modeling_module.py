import argparse
import os
import subprocess
from subprocess import call
import sys
import glob
from modeling_variables import *


def has_colours(stream):
    if not hasattr(stream, "isatty"):
        return False
    if not stream.isatty():
        return False  # auto color only on TTYs
    try:
        import curses

        curses.setupterm()
        return curses.tigetnum("colors") > 2
    except:
        # guess false in case of error
        return False


def printout(has_colours, text, colour=WHITE, background=BLACK, effect=NO_EFFECT):
    if has_colours:
        seq = (
            "\x1b[{};{};{}m".format(effect, 30 + colour, 40 + background)
            + text
            + "\x1b[0m"
        )
        sys.stdout.write(seq + "\r\n")
    else:
        sys.stdout.write(text + "\r\n")


class ConfContainer(object):
    def __init__(self, input_dir, output_dir):
        self.input_dir = input_dir
        self.output_dir = output_dir


class aStep:
    def __init__(self, info, cmd, opt):
        self.info = info
        self.cmd = cmd
        self.opt = opt


class stepsStore:
    def __init__(self):

        self.steps_data = [
            [
                "Intrinsics analysis",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_SfMInit_ImageListing"),
                [
                    "-i",
                    "%input_dir%",
                    "-o",
                    "%matches_dir%",
                    "-d",
                    "%camera_file_params%",
                    "-g",
                    "0",
                ],
            ],
            [
                "Compute features",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_ComputeFeatures"),
                [
                    "-i",
                    "%matches_dir%/sfm_data.json",
                    "-o",
                    "%matches_dir%",  # , "-f", "1"
                    "-p",
                    "ULTRA",
                    "-n",
                    "3",
                    # "-m",
                    # "AKAZE_FLOAT",
                ],
            ],
            [
                "Compute matches",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_ComputeMatches"),
                [
                    "-i",
                    "%matches_dir%/sfm_data.json",
                    "-o",
                    "%matches_dir%",
                    "-n",
                    "ANNL2",
                    "-r",
                    "0.6",
                ],
            ],
            [
                "Incremental reconstruction",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_IncrementalSfM2"),
                [
                    "-i",
                    "%matches_dir%/sfm_data.json",
                    "-m",
                    "%matches_dir%",
                    "-o",
                    "%reconstruction_dir%"  # , "-M", "%matches_dir%/matches.h.bin"
                    # , "-f", "NONE"
                    ,
                    "-S",
                    "STELLAR",
                    "-t",
                    "2",
                ],
            ],
            [
                "Export to openMVS",
                os.path.join(OPENMVG_SFM_BIN, "openMVG_main_openMVG2openMVS"),
                [
                    "-i",
                    "%reconstruction_dir%/sfm_data.bin",
                    "-o",
                    "%mvs_dir%/scene.mvs",
                    "-d",
                    "%mvs_dir%",
                ],
            ],
            [
                "Densify point cloud",
                os.path.join(OPENMVS_BIN, "DensifyPointCloud"),
                [
                    "--input-file",
                    "%mvs_dir%/scene.mvs",
                    "-w",
                    "%mvs_dir%",
                ],
            ],
            [
                "Reconstruct the mesh",
                os.path.join(OPENMVS_BIN, "ReconstructMesh"),
                [
                    "%mvs_dir%/scene_dense.mvs",
                    "-w",
                    "%mvs_dir%",
                    "--remove-spurious",
                    "50",
                    "-f",
                    "true",
                ],
            ],
            [
                "Refine the mesh",
                os.path.join(OPENMVS_BIN, "RefineMesh"),
                [
                    "%mvs_dir%/scene_dense_mesh.mvs",
                    "-w",
                    "%mvs_dir%",
                    "--decimate",
                    "0.7",
                ],
            ],
            [
                "Texture the mesh",
                os.path.join(OPENMVS_BIN, "TextureMesh"),
                [
                    "%mvs_dir%/scene_dense_mesh_refine.mvs",
                    "-w",
                    "%mvs_dir%",
                    "--patch-packing-heuristic",
                    "0",
                    "--export-type",
                    "obj",
                ],
            ],
        ]

    def __getitem__(self, indice):
        return aStep(*self.steps_data[indice])

    def length(self):
        return len(self.steps_data)

    def apply_conf(self, conf):
        """ replace each %var% per conf.var value in steps data """
        for s in self.steps_data:
            o2 = []
            for o in s[2]:
                co = o.replace("%input_dir%", conf.input_dir)
                co = co.replace("%output_dir%", conf.output_dir)
                co = co.replace("%matches_dir%", conf.matches_dir)
                co = co.replace("%reconstruction_dir%", conf.reconstruction_dir)
                co = co.replace("%mvs_dir%", conf.mvs_dir)
                co = co.replace("%camera_file_params%", conf.camera_file_params)
                o2.append(co)
            s[2] = o2


def setArgs(conf, steps):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Photogrammetry reconstruction with these steps : \r\n"
        + "\r\n".join(
            (
                "\t{}. {}\t {}".format(t, steps[t].info, steps[t].cmd)
                for t in range(steps.length())
            )
        ),
    )
    parser.add_argument(
        "-f", "--first_step", type=int, default=0, help="the first step to process"
    )
    parser.add_argument(
        "-l", "--last_step", type=int, default=8, help="the last step to process"
    )

    group = parser.add_argument_group(
        "Passthrough",
        description="Option to be passed to command lines (remove - in front of option names)\r\ne.g. --1 p ULTRA to use the ULTRA preset in openMVG_main_ComputeFeatures",
    )
    for n in range(steps.length()):
        group.add_argument("--" + str(n), nargs="+")

    parser.parse_args(namespace=conf)  # store args in the ConfContainer


def mkdir_ine(dirname):
    """Create the folder if not presents"""
    if not os.path.exists(dirname):
        os.mkdir(dirname)


def setConfs(conf):
    conf.matches_dir = os.path.join(conf.output_dir, "matches")
    conf.reconstruction_dir = os.path.join(conf.output_dir, "reconstruction_sequential")
    conf.mvs_dir = os.path.join(conf.output_dir, "mvs")
    conf.camera_file_params = os.path.join(
        CAMERA_SENSOR_WIDTH_DIRECTORY, "sensor_width_camera_database.txt"
    )

    mkdir_ine(conf.output_dir)
    mkdir_ine(conf.matches_dir)
    mkdir_ine(conf.reconstruction_dir)
    mkdir_ine(conf.mvs_dir)


def check_step_success(step, outputPath):
    if step == 0 or step == 1 or step == 2:
        result_folder = "matches"
    elif step == 3:
        result_folder = "reconstruction_sequential"
    else:
        result_folder = "mvs"

    result_path = os.path.join(outputPath, result_folder)

    if step == 0:
        file_list = glob.glob(os.path.join(result_path, "*.json"))
    elif step == 1:
        file_list = glob.glob(os.path.join(result_path, "*.desc"))
    elif step == 2:
        file_list = glob.glob(os.path.join(result_path, "*.bin"))
    elif step == 3:
        file_list = glob.glob(os.path.join(result_path, "*.bin"))
    elif step == 4:
        file_list = glob.glob(os.path.join(result_path, "scene.mvs"))
    elif step == 5:
        file_list = glob.glob(os.path.join(result_path, "scene_dense.mvs"))
    elif step == 6:
        file_list = glob.glob(os.path.join(result_path, "scene_dense_mesh.mvs"))
    elif step == 7:
        file_list = glob.glob(os.path.join(result_path, "scene_dense_mesh_refine.mvs"))
    else:
        file_list = glob.glob(
            os.path.join(result_path, "scene_dense_mesh_refine_texture.mvs")
        )

    if file_list:
        return True
    else:
        return False
