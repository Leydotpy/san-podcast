import enum
from core.application import AppConfig

VIDEO_EXTENSIONS = ("MP4", "AVI", "FLV", "MKV", "3GP", "WebM", "WMV", "MOV", "MPEG")
AUDIO_EXTENSIONS = ("MP3", "WAV", "AAC", "WMA", "FLAC", "M4A", "AIFF", "AMR", "MIDI")


class Positions(enum.StrEnum):
    ...

GK = "GK"
SWK = "SWK"
RB = "RB"
LB = "LB"
LWB = "LWB"
RWB = "RWB"
CBC = "CBC"
CBR = "CWR"
CBL = "CWL"
DMF = "DMF"
CMF = "CMF"
CMR = "CMR"
CML = "CML"
CAM = "CAM"
LM = "LM"
RM = "RM"
RWF = "RWF"
LWF = "LWF"
SS = "SS"
ST = "ST"
RST = "RST"
LST = "LST"
CF = "CF"


POSITION_MAP = {
    "4-4-2": {
        "DEFAULT": {
            GK: {"top": 90, "left": 50},
            SWK: {"top": 90, "left": 50},
            CBL: {"top": 70, "left": 35},
            CBR: {"top": 70, "left": 65},
            RB: {"top": 70, "left": 80},
            LB: {"top": 70, "left": 20},
            LM: {"top": 50, "left": 20},
            RM: {"top": 50, "left": 80},
            CMR: {"top": 50, "left": 40},
            CML: {"top": 50, "left": 60},
            LST: {"top": 30, "left": 40},
            RST: {"top": 30, "left": 60},
        },
        "DIAMOND": {

        }
    },
    "4-3-3": {
        "DEFAULT": {
            GK: {"top": 90, "left": 50},
            SWK: {"top": 90, "left": 50},
            CBL: {"top": 70, "left": 35},
            CBR: {"top": 70, "left": 65},
            RB: {"top": 70, "left": 80},
            LB: {"top": 70, "left": 20},
            CMR: {"top": 50, "left": 33},
            CML: {"top": 50, "left": 50},
            CMF: {"top": 50, "left": 67},
            LWF: {"top": 30, "left": 20},
            RWF: {"top": 30, "left": 50},
            CF: {"top": 30, "left": 80},
        }
    },
    "4-3-1-2": {
        "DEFAULT": {
            GK: {"top": 90, "left": 50},
            SWK: {"top": 90, "left": 50},
            CBL: {"top": 70, "left": 35},
            CBR: {"top": 70, "left": 65},
            RB: {"top": 70, "left": 80},
            LB: {"top": 70, "left": 20},
            CMR: {"top": 60, "left": 33},
            CMF: {"top": 60, "left": 50},
            CML: {"top": 60, "left": 67},
            CAM: {"top": 40, "left": 50},
            RST: {"top": 20, "left": 40},
            LST: {"top": 20, "left": 60},
        }
    },
    "3-5-2": {
        "DEFAULT": {
            GK: {"top": 90, "left": 50},
            SWK: {"top": 90, "left": 50},
            CBL: {"top": 70, "left": 33},
            CBC: {"top": 70, "left": 50},
            CBR: {"top": 70, "left": 67},
            LWB: {"top": 50, "left": 20},
            RWB: {"top": 50, "left": 80},
            CMR: {"top": 50, "left": 35},
            CML: {"top": 50, "left": 65},
            LWF: {"top": 30, "left": 20},
            RWF: {"top": 30, "left": 80},
            CF: {"top": 30, "left": 50},
        }
    }
}


class Config(AppConfig):
    name = 'apps'
