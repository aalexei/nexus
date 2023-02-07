##
## Copyright 2010-2022 Alexei Gilchrist
##
## This file is part of Nexus.
##
## Nexus is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Nexus is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Nexus.  If not, see <http://www.gnu.org/licenses/>.

from pathlib import Path
from importlib.machinery import SourceFileLoader

default_config = {
    #
    # context menu
    #

    # long press timeout in ms
    "long_press_time":800,

    # number of pixels that are considered no-movement for press and hold.
    "no_move_threshold":2,

    #
    # pinch gesture
    #
    "pinch_no_move_threshold": 0,  # view pixels
    "pinch_no_rotate_threshold": 20, # degrees
    "pinch_no_scale_threshold": [0.92, 1.08], # scale factors

    #
    # input dialog
    #
    # completely ignore mouse moves when using pen
    "input_ignore_mouse": False,
    # mouse pans display when using pen
    "input_mouse_moves": False,

    # quadratic Bezier (0,0)-(x1,y1)-(1,1) 
    "pressure_curve":{'x1':0.2, 'y1':0.8},

    #
    # text item
    #

    # Default size of textbox
    "text_item_width": 380,

    #
    # font
    #

    # Bundling ETBembo with Nexus
    "text_item_font_family": "ETBembo",
    "text_item_font_size": 12,
    # TODO retina screen halves the size? Get more consistent sizing across platforms
    "text_item_color": "#000000",

    #
    # laser trail
    # Colour format: #AARRGGBB
    #
    "trail_outer_color": "#EE00E000",
    "trail_inner_color": "#BBFFFFFF",
    "trail_outer_width": 14,
    "trail_inner_width": 4,
    "trail_pointer_factor": 1.5, # factor to increase pointer size by
    "trail_hold_time": 1.0, # how long to keep the trail after pointer-up [in seconds]

    #
    # Presentation Mode
    #
    "view_next_keys": ["PgDown","Right", "Down", " "],
    "view_prev_keys": ["PgUp","Left", "Up"],
    "view_home_keys": [".", "H"],
    "view_first_keys": ["0", "S"],
    "view_pointer_keys": ["P"],

    #
    # Recording
    #
    "recording_countdown": 3,

    #
    # Icon size
    #
    "icon_size": 26,
}


def get_config():

    config = default_config.copy()

    # any of these config files should define a config dictionary with keys to update
    # the default config

    # TODO make robust against errors in config files
    possible_configs = [
        Path("~/Library/Application Support/Nexus/config.py").expanduser(),
        Path("~/.config/nexus/config.py").expanduser(),
    ]

    for c in possible_configs:
        if c.exists():
            mod = SourceFileLoader("", c.as_posix()).load_module()
            config.update(mod.config)

    return config
