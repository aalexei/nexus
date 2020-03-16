##
## Copyright 2010-2019 Alexei Gilchrist
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
    "pinch_no_scale_threshold": [0.9, 1.1], # scale factors

    #
    # input dialog
    #

    "input_ignore_mouse": False,

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
    "text_item_color": "#000000",
}


def get_config():

    config = default_config.copy()

    possible_configs = [
        Path("~/Library/Application Support/Ook/config.py").expanduser(),
        Path("~/.config/ook/config.py").expanduser(),
    ]

    for c in possible_configs:
        if c.exists():
            mod = SourceFileLoader("", c.as_posix()).load_module()
            config.update(mod.config)

    return config
