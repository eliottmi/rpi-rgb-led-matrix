"""Definition of programs the web UI can launch.

Each program is a metadata description used to:
  - build a dynamic HTML form,
  - validate the submitted values,
  - build the argv list to spawn the binary.

Option types supported by the form builder:
  - "string"     : plain text input
  - "int"        : integer input
  - "float"      : floating-point input
  - "bool"       : checkbox; when checked the flag is added with no value
  - "select"     : <select> with an "options" list (list of (value, label))
  - "color"      : "r,g,b" text input rendered as a color picker
  - "file"       : path to an existing file picked from the listed directories
                   (the option's "dirs" key gives a list of subdirectories
                   under REPO_ROOT to search; the "exts" key filters by
                   extension)

Each option may have:
  - flag:     the command-line flag (e.g. "--led-rows", "-f")
  - default:  default value used when the user leaves the field empty
  - help:     short text shown next to the field
  - omit_if_default: when True, do not pass the flag when the value equals
                    the default (keeps the command line small).
"""

# Shared LED matrix flags. Reused by every program.
LED_MATRIX_OPTIONS = [
    {
        "name": "led-gpio-mapping",
        "flag": "--led-gpio-mapping",
        "type": "select",
        "default": "regular",
        "options": [
            ("regular", "regular"),
            ("adafruit-hat", "adafruit-hat"),
            ("adafruit-hat-pwm", "adafruit-hat-pwm"),
            ("regular-pi1", "regular-pi1"),
            ("classic", "classic"),
            ("classic-pi1", "classic-pi1"),
        ],
        "help": "GPIO mapping (hardware)",
        "omit_if_default": True,
    },
    {
        "name": "led-rows", "flag": "--led-rows", "type": "int",
        "default": 32, "help": "Rows per panel (8/16/32/64)",
    },
    {
        "name": "led-cols", "flag": "--led-cols", "type": "int",
        "default": 32, "help": "Columns per panel (32/64)",
    },
    {
        "name": "led-chain", "flag": "--led-chain", "type": "int",
        "default": 1, "help": "Number of daisy-chained panels",
    },
    {
        "name": "led-parallel", "flag": "--led-parallel", "type": "int",
        "default": 1, "help": "Number of parallel chains (1..3)",
    },
    {
        "name": "led-brightness", "flag": "--led-brightness", "type": "int",
        "default": 100, "help": "Brightness 1..100",
    },
    {
        "name": "led-pwm-bits", "flag": "--led-pwm-bits", "type": "int",
        "default": 11, "help": "PWM bits 1..11", "omit_if_default": True,
    },
    {
        "name": "led-pwm-lsb-nanoseconds",
        "flag": "--led-pwm-lsb-nanoseconds", "type": "int",
        "default": 130, "help": "PWM nanoseconds for LSB",
        "omit_if_default": True,
    },
    {
        "name": "led-pwm-dither-bits",
        "flag": "--led-pwm-dither-bits", "type": "int",
        "default": 0, "help": "Time dithering of lower bits (0..2)",
        "omit_if_default": True,
    },
    {
        "name": "led-scan-mode", "flag": "--led-scan-mode", "type": "select",
        "default": "0",
        "options": [("0", "0 progressive"), ("1", "1 interlaced")],
        "help": "Scan mode", "omit_if_default": True,
    },
    {
        "name": "led-row-addr-type", "flag": "--led-row-addr-type",
        "type": "select", "default": "0",
        "options": [
            ("0", "0 default"),
            ("1", "1 AB-addressed"),
            ("2", "2 direct row select"),
            ("3", "3 ABC-addressed"),
            ("4", "4 ABC shift + DE direct"),
        ],
        "help": "Row address type", "omit_if_default": True,
    },
    {
        "name": "led-multiplexing", "flag": "--led-multiplexing",
        "type": "select", "default": "0",
        "options": [(str(i), str(i)) for i in range(18)],
        "help": "Multiplexing mapper (0=direct, see README)",
        "omit_if_default": True,
    },
    {
        "name": "led-pixel-mapper", "flag": "--led-pixel-mapper",
        "type": "string", "default": "",
        "help": 'e.g. "U-mapper;Rotate:90"',
    },
    {
        "name": "led-rgb-sequence", "flag": "--led-rgb-sequence",
        "type": "string", "default": "RGB",
        "help": "RGB sequence (default RGB)", "omit_if_default": True,
    },
    {
        "name": "led-slowdown-gpio", "flag": "--led-slowdown-gpio",
        "type": "int", "default": 1,
        "help": "GPIO slowdown (0..4)", "omit_if_default": True,
    },
    {
        "name": "led-limit-refresh", "flag": "--led-limit-refresh",
        "type": "int", "default": 0,
        "help": "Limit refresh rate (Hz); 0=no limit",
        "omit_if_default": True,
    },
    {
        "name": "led-panel-type", "flag": "--led-panel-type",
        "type": "select", "default": "",
        "options": [("", "(none)"), ("FM6126A", "FM6126A"), ("FM6127", "FM6127")],
        "help": "Special panel type (if needed)",
    },
    {
        "name": "led-show-refresh", "flag": "--led-show-refresh",
        "type": "bool", "default": False, "help": "Print refresh rate",
    },
    {
        "name": "led-inverse", "flag": "--led-inverse",
        "type": "bool", "default": False,
        "help": "Invert colors (for inverse panels)",
    },
    {
        "name": "led-no-hardware-pulse", "flag": "--led-no-hardware-pulse",
        "type": "bool", "default": False,
        "help": "Disable hardware pin-pulse generation",
    },
    {
        "name": "led-no-drop-privs", "flag": "--led-no-drop-privs",
        "type": "bool", "default": False,
        "help": "Keep root privileges after init",
    },
]


def _font_file(name="font", flag="-f", default="", required=False,
               help_text="BDF font file"):
    return {
        "name": name, "flag": flag, "type": "file", "default": default,
        "required": required, "help": help_text,
        "dirs": ["fonts"], "exts": [".bdf"],
    }


def _image_file(name="image", flag=None, default="", required=False,
                help_text="Image file"):
    return {
        "name": name, "flag": flag, "type": "file", "default": default,
        "required": required, "help": help_text,
        "dirs": ["examples-api-use", "webserver/uploads"],
        "exts": [".ppm", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
                 ".stream"],
        "positional": flag is None,
    }


# Each program entry:
#   id, name, description, binary (path relative to repo root),
#   build_dir (where to run `make` to build it), build_target (make target),
#   needs_root (use sudo), specific_options (list of option dicts),
#   positional (list of option names that should be passed without a flag at
#               the end of the argv -- in this order)
PROGRAMS = [
    {
        "id": "demo",
        "name": "Démo (demo-main)",
        "description":
            "Démonstrations diverses sélectionnées avec -D : carrés, "
            "scrolls, jeu de la vie, etc.",
        "binary": "examples-api-use/demo",
        "build_dir": "examples-api-use",
        "build_target": "demo",
        "needs_root": True,
        "specific_options": [
            {
                "name": "demo", "flag": "-D", "type": "select",
                "default": "0", "required": True,
                "options": [
                    ("0",  "0 - rotating square"),
                    ("1",  "1 - forward scrolling image"),
                    ("2",  "2 - backward scrolling image"),
                    ("3",  "3 - test image (square)"),
                    ("4",  "4 - pulsing color"),
                    ("5",  "5 - grayscale block"),
                    ("6",  "6 - Abelian sandpile"),
                    ("7",  "7 - Conway's game of life"),
                    ("8",  "8 - Langton's ant"),
                    ("9",  "9 - volume bars"),
                    ("10", "10 - evolution of color"),
                    ("11", "11 - brightness pulse"),
                ],
                "help": "Demo number",
            },
            {
                "name": "delay", "flag": "-m", "type": "int", "default": 0,
                "help": "Time-step / scroll ms (demos 1,2,6,7,8,9,10)",
                "omit_if_default": True,
            },
            _image_file(help_text="Image (required for demos 1 and 2, e.g. runtext.ppm)"),
        ],
        "positional": ["image"],
    },
    {
        "id": "minimal-example",
        "name": "Minimal example",
        "description": "Programme minimal d'exemple : remplit la matrice "
                       "puis efface en boucle.",
        "binary": "examples-api-use/minimal-example",
        "build_dir": "examples-api-use",
        "build_target": "minimal-example",
        "needs_root": True,
        "specific_options": [],
    },
    {
        "id": "text-example",
        "name": "Text (stdin)",
        "description":
            "Lit du texte sur stdin et l'affiche (envoyez le texte via le "
            "champ ci-dessous; il est passé sur l'entrée standard).",
        "binary": "examples-api-use/text-example",
        "build_dir": "examples-api-use",
        "build_target": "text-example",
        "needs_root": True,
        "stdin_field": "stdin_text",
        "specific_options": [
            _font_file(required=True, default="fonts/8x13.bdf"),
            {"name": "x", "flag": "-x", "type": "int", "default": 0,
             "help": "X origin", "omit_if_default": True},
            {"name": "y", "flag": "-y", "type": "int", "default": 0,
             "help": "Y origin", "omit_if_default": True},
            {"name": "spacing", "flag": "-S", "type": "int", "default": 0,
             "help": "Letter spacing", "omit_if_default": True},
            {"name": "color", "flag": "-C", "type": "color",
             "default": "255,255,0", "help": "Text color"},
            {"name": "bg", "flag": "-B", "type": "color",
             "default": "0,0,0", "help": "Background color"},
            {"name": "outline", "flag": "-O", "type": "color",
             "default": "", "help": "Outline color (optional)"},
            {"name": "flood", "flag": "-F", "type": "color",
             "default": "", "help": "Panel flooding color"},
            {"name": "stdin_text", "type": "string", "default": "",
             "help": "Texte envoyé sur stdin (une ligne par retour)",
             "multiline": True, "stdin_only": True},
        ],
    },
    {
        "id": "scrolling-text-example",
        "name": "Scrolling text",
        "description": "Affiche un texte qui défile.",
        "binary": "examples-api-use/scrolling-text-example",
        "build_dir": "examples-api-use",
        "build_target": "scrolling-text-example",
        "needs_root": True,
        "specific_options": [
            _font_file(required=True, default="fonts/9x18.bdf"),
            {"name": "speed", "flag": "-s", "type": "float", "default": 7,
             "help": "Letters per second (negative = left-to-right)"},
            {"name": "loops", "flag": "-l", "type": "int", "default": -1,
             "help": "Loop count (-1 = forever)", "omit_if_default": True},
            {"name": "x", "flag": "-x", "type": "int", "default": 0,
             "help": "X origin", "omit_if_default": True},
            {"name": "y", "flag": "-y", "type": "int", "default": 0,
             "help": "Y origin", "omit_if_default": True},
            {"name": "spacing", "flag": "-t", "type": "int", "default": 0,
             "help": "Letter spacing", "omit_if_default": True},
            {"name": "color", "flag": "-C", "type": "color",
             "default": "255,255,255", "help": "Text color"},
            {"name": "bg", "flag": "-B", "type": "color",
             "default": "0,0,0", "help": "Background color"},
            {"name": "text", "type": "string", "default": "Hello World",
             "required": True, "help": "Texte à afficher"},
        ],
        "positional": ["text"],
    },
    {
        "id": "clock",
        "name": "Horloge",
        "description": "Affiche une horloge / date formatée.",
        "binary": "examples-api-use/clock",
        "build_dir": "examples-api-use",
        "build_target": "clock",
        "needs_root": True,
        "specific_options": [
            _font_file(required=True, default="fonts/7x13.bdf"),
            {"name": "format", "flag": "-d", "type": "string",
             "default": "%H:%M:%S",
             "help": "strftime format (peut être répété, séparé par |)"},
            {"name": "x", "flag": "-x", "type": "int", "default": 0,
             "help": "X origin", "omit_if_default": True},
            {"name": "y", "flag": "-y", "type": "int", "default": 0,
             "help": "Y origin", "omit_if_default": True},
            {"name": "line_spacing", "flag": "-s", "type": "int",
             "default": 0, "help": "Espacement entre lignes",
             "omit_if_default": True},
            {"name": "spacing", "flag": "-S", "type": "int", "default": 0,
             "help": "Espacement entre lettres", "omit_if_default": True},
            {"name": "color", "flag": "-C", "type": "color",
             "default": "255,255,0", "help": "Couleur"},
            {"name": "bg", "flag": "-B", "type": "color",
             "default": "0,0,0", "help": "Couleur d'arrière-plan"},
            {"name": "outline", "flag": "-O", "type": "color",
             "default": "", "help": "Couleur de contour"},
        ],
    },
    {
        "id": "image-example",
        "name": "Image (GraphicsMagick)",
        "description":
            "Affiche une image. Nécessite GraphicsMagick++ "
            "(libgraphicsmagick++-dev).",
        "binary": "examples-api-use/image-example",
        "build_dir": "examples-api-use",
        "build_target": "image-example",
        "needs_root": True,
        "specific_options": [
            _image_file(flag="-i", required=True,
                        help_text="Image (PNG, JPG, GIF, PPM...)"),
            {"name": "wait", "flag": "-w", "type": "float", "default": 1.5,
             "help": "Wait time before scrolling/next image (s)",
             "omit_if_default": True},
        ],
    },
    {
        "id": "pixel-mover",
        "name": "Pixel mover (snake-like)",
        "description":
            "Déplace un pixel avec W/A/S/D (envoyé sur stdin). Utile pour "
            "tester le mapping. Pour le piloter, tapez la séquence de "
            "touches dans le champ stdin.",
        "binary": "examples-api-use/pixel-mover",
        "build_dir": "examples-api-use",
        "build_target": "pixel-mover",
        "needs_root": True,
        "stdin_field": "stdin_text",
        "specific_options": [
            {"name": "color", "flag": "-C", "type": "color",
             "default": "255,255,0", "help": "Couleur du pixel"},
            {"name": "trail", "flag": "-t", "type": "int", "default": 0,
             "help": "Longueur de la traînée", "omit_if_default": True},
            {"name": "end_color", "flag": "-c", "type": "color",
             "default": "0,0,255", "help": "Couleur en bout de traînée"},
            {"name": "stdin_text", "type": "string", "default": "",
             "help": "Suite de touches W/A/S/D envoyée sur stdin",
             "stdin_only": True},
        ],
    },
    {
        "id": "led-image-viewer",
        "name": "Image viewer (utils)",
        "description":
            "Visionneuse d'images (PNG, JPG, GIF animé...). Nécessite "
            "GraphicsMagick++.",
        "binary": "utils/led-image-viewer",
        "build_dir": "utils",
        "build_target": "led-image-viewer",
        "needs_root": True,
        "specific_options": [
            _image_file(required=True),
            {"name": "wait", "flag": "-w", "type": "float", "default": 1.5,
             "help": "Wait time between images (s) - statiques",
             "omit_if_default": True},
            {"name": "time", "flag": "-t", "type": "float", "default": 0,
             "help": "Animations: stop après N secondes",
             "omit_if_default": True},
            {"name": "loops", "flag": "-l", "type": "int", "default": 0,
             "help": "Animations: nombre de boucles",
             "omit_if_default": True},
            {"name": "frame_delay", "flag": "-D", "type": "int",
             "default": -1, "help": "Animations: override frame delay (ms)",
             "omit_if_default": True},
            {"name": "forever", "flag": "-f", "type": "bool",
             "default": False, "help": "Cycle forever"},
            {"name": "shuffle", "flag": "-s", "type": "bool",
             "default": False, "help": "Shuffle order"},
            {"name": "center", "flag": "-C", "type": "bool",
             "default": False, "help": "Center images"},
        ],
        "positional": ["image"],
    },
    {
        "id": "text-scroller",
        "name": "Text scroller (utils)",
        "description": "Scroller de texte autonome.",
        "binary": "utils/text-scroller",
        "build_dir": "utils",
        "build_target": "text-scroller",
        "needs_root": True,
        "specific_options": [
            _font_file(required=True, default="fonts/9x18.bdf"),
            {"name": "speed", "flag": "-s", "type": "float", "default": 7,
             "help": "Letters per second (negative = left-to-right)"},
            {"name": "loops", "flag": "-l", "type": "int", "default": -1,
             "help": "Loop count (-1 = forever)", "omit_if_default": True},
            {"name": "x", "flag": "-x", "type": "int", "default": 0,
             "help": "X origin", "omit_if_default": True},
            {"name": "y", "flag": "-y", "type": "int", "default": 0,
             "help": "Y origin", "omit_if_default": True},
            {"name": "spacing", "flag": "-t", "type": "int", "default": 0,
             "help": "Letter spacing", "omit_if_default": True},
            {"name": "color", "flag": "-C", "type": "color",
             "default": "255,255,255", "help": "Text color"},
            {"name": "bg", "flag": "-B", "type": "color",
             "default": "0,0,0", "help": "Background color"},
            {"name": "outline", "flag": "-O", "type": "color",
             "default": "", "help": "Outline color"},
            {"name": "text", "type": "string", "default": "Hello World",
             "required": True, "help": "Texte à afficher"},
        ],
        "positional": ["text"],
    },
    {
        "id": "video-viewer",
        "name": "Video viewer (utils)",
        "description":
            "Visionneuse de vidéos (libav). Nécessite "
            "libavcodec/libavformat/libswscale-dev.",
        "binary": "utils/video-viewer",
        "build_dir": "utils",
        "build_target": "video-viewer",
        "needs_root": True,
        "specific_options": [
            _image_file(required=True, help_text="Fichier vidéo"),
            {"name": "fullscreen", "flag": "-F", "type": "bool",
             "default": False, "help": "Plein écran (ignore aspect ratio)"},
            {"name": "skip", "flag": "-s", "type": "int", "default": 0,
             "help": "Skip frames", "omit_if_default": True},
            {"name": "count", "flag": "-c", "type": "int", "default": 0,
             "help": "Show only N frames (0 = all)",
             "omit_if_default": True},
            {"name": "vsync", "flag": "-V", "type": "int", "default": 0,
             "help": "Vsync multiple", "omit_if_default": True},
            {"name": "threads", "flag": "-T", "type": "int", "default": 1,
             "help": "Decoder threads (1..4)", "omit_if_default": True},
            {"name": "verbose", "flag": "-v", "type": "bool",
             "default": False, "help": "Verbose"},
            {"name": "forever", "flag": "-f", "type": "bool",
             "default": False, "help": "Loop forever"},
        ],
        "positional": ["image"],
    },
]


def get_program(prog_id):
    for p in PROGRAMS:
        if p["id"] == prog_id:
            return p
    return None


def all_options(program):
    """Yield common LED matrix options followed by program-specific ones."""
    for opt in LED_MATRIX_OPTIONS:
        yield opt
    for opt in program.get("specific_options", []):
        yield opt
