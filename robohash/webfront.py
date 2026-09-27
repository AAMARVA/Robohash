#!/usr/bin/env python3

# Find details about this project at https://github.com/e1ven/robohash
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import socket
import os
import hashlib
import random
from robohash import Robohash
import re
import io
import base64

import time
from collections import defaultdict, deque

from tornado.options import define, options

define("port", default=int(os.environ.get("PORT", 80)), help="run on the given port", type=int)

# Exact CORS allowlist - reject every other origin. No wildcards, no reflection.
APPROVED_ORIGINS = {
    "https://aamarva.com",
    "https://ais-dev-sy4lhzb3bv4g4mm7spkr5c-89865814157.asia-southeast1.run.app",
}

class RateLimiter:
    """
    In-memory rate limiter using a sliding-window counter per client IP.
    """
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        q = self.requests[key]
        while q and q[0] <= now - self.window_seconds:
            q.popleft()
        if len(q) >= self.max_requests:
            return False
        q.append(now)
        return True

    def clear(self):
        self.requests.clear()

rate_limiter = RateLimiter(
    max_requests=int(os.environ.get("RATE_LIMIT_MAX", "60")),
    window_seconds=int(os.environ.get("RATE_LIMIT_WINDOW", "60")),
)

class SecurityMixin:
    def check_origin_and_rate_limit(self) -> bool:
        """
        Validates the Origin header and applies rate limiting.
        - CORS allows ONLY approved origins.
        - Disallowed origins are rejected with 403 Forbidden.
        - Approved origins bypass rate limiting completely.
        - Requests without an approved origin are subject to rate limiting.
        """
        origin = self.request.headers.get("Origin")
        if origin is not None:
            if origin not in APPROVED_ORIGINS:
                self.set_status(403)
                self.finish("Forbidden: Origin not allowed")
                return False
            # Approved origin: set exact CORS headers and bypass rate limiting
            self.set_header("Access-Control-Allow-Origin", origin)
            self.set_header("Vary", "Origin")
            self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            return True

        # Direct requests without Origin header: enforce rate limiting
        client_ip = self.request.remote_ip or "unknown"
        if not rate_limiter.is_allowed(client_ip):
            self.set_status(429)
            self.set_header("Retry-After", str(rate_limiter.window_seconds))
            self.finish("Too Many Requests: Rate limit exceeded")
            return False

        return True

    def handle_options(self):
        origin = self.request.headers.get("Origin")
        if origin is not None:
            if origin not in APPROVED_ORIGINS:
                self.set_status(403)
                self.finish("Forbidden: Origin not allowed")
                return
            self.set_header("Access-Control-Allow-Origin", origin)
            self.set_header("Vary", "Origin")
            self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.set_header("Access-Control-Max-Age", "86400")
            self.set_status(204)
            self.finish()
            return
        self.set_status(204)
        self.finish()

class MainHandler(tornado.web.RequestHandler, SecurityMixin):
    def prepare(self):
        if not self.check_origin_and_rate_limit():
            return

    def options(self, *args, **kwargs):
        self.handle_options()
    def get(self):
        ip = self.request.remote_ip

        robo = [
"""
                     ,     ,
                     (\\____/)
                        (_oo_)
                            (O)
                        __||__    \\)
                 []/______\\[] /
                 / \\______/ \\/
                /    /__\\
             (\\   /____\\ """,
"""
                             _______
                         _/       \\_
                        / |       | \\
                     /  |__   __|  \\
                    |__/((o| |o))\\__|
                    |      | |      |
                    |\\     |_|     /|
                    | \\           / |
                     \\| /  ___  \\ |/
                        \\ | / _ \\ | /
                         \\_________/
                            _|_____|_
                 ____|_________|____
                /                   \\  -- Mark Moir


""",
"""                     .andAHHAbnn.
                                     .aAHHHAAUUAAHHHAn.
                                    dHP^~"        "~^THb.
                        .   .AHF                YHA.   .
                        |  .AHHb.              .dHHA.  |
                        |  HHAUAAHAbn      adAHAAUAHA  |
                        I  HF~"_____        ____ ]HHH  I
                     HHI HAPK""~^YUHb  dAHHHHHHHHHH IHH
                     HHI HHHD> .andHH  HHUUP^~YHHHH IHH
                     YUI ]HHP     "~Y  P~"     THH[ IUP
                        "  `HK                   ]HH'  "
                                THAn.  .d.aAAn.b.  .dHHP
                                ]HHHHAAUP" ~~ "YUAAHHHH[
                                `HHP^~"  .annn.  "~^YHH'
                                 YHb    ~" "" "~    dHF
                                    "YAb..abdHHbndbndAP"
                                     THHAAb.  .adAHHF
                                        "UHHHHHHHHHHU"
                                            ]HHUUHHHHHH[
                                        .adHHb "HHHHHbn.
                         ..andAAHHHHHHb.AHHHHHHHAAbnn..
                .ndAAHHHHHHUUHHHHHHHHHHUP^~"~^YUHHHAAbn.
                    "~^YUHHP"   "~^YUHHUP"        "^YUP^"
                             ""         "~~"
""",
"""                                 /~@@~\\,
                                _______ . _\\_\\___/\\ __ /\\___|_|_ . _______
                             / ____  |=|      \\  <_+>  /      |=|  ____ \\
                             ~|    |\\|=|======\\\\______//======|=|/|    |~
                                |_   |    \\      |      |      /    |    |
                                 \\==-|     \\     |  2D  |     /     |----|~~)
                                 |   |      |    |      |    |      |____/~/
                                 |   |       \\____\\____/____/      /    / /
                                 |   |         {----------}       /____/ /
                                 |___|        /~~~~~~~~~~~~\\     |_/~|_|/
                                    \\_/        [/~~~~~||~~~~~\\]     /__|\\
                                    | |         |    ||||    |     (/|[[\\)
                                    [_]        |     |  |     |
                                                         |_____|  |_____|
                                                         (_____)  (_____)
                                                         |     |  |     |
                                                         |     |  |     |
                                                         |/~~~\\|  |/~~~\\|
                                                         /|___|\\  /|___|\\
                                                        <_______><_______>""",
"""                                      _____
                                                                            /_____\\
                                                                 ____[\\`---'/]____
                                                                /\\ #\\ \\_____/ /# /\\
                                                             /  \\# \\_.---._/ #/  \\
                                                            /   /|\\  |   |  /|\\   \\
                                                         /___/ | | |   | | | \\___\\
                                                         |  |  | | |---| | |  |  |
                                                         |__|  \\_| |_#_| |_/  |__|
                                                         //\\\\  <\\ _//^\\\\_ />  //\\\\
                                                         \\||/  |\\//// \\\\\\\\/|  \\||/
                                                                     |   |   |   |
                                                                     |---|   |---|
                                                                     |---|   |---|
                                                                     |   |   |   |
                                                                     |___|   |___|
                                                                     /   \\   /   \\
                                                                    |_____| |_____|
                                                                    |HHHHH| |HHHHH|
                                                        """,
"""                                        ()               ()
                                                                                    \\             /
                                                                                 __\\___________/__
                                                                                /                 \\
                                                                             /     ___    ___    \\
                                                                             |    /   \\  /   \\   |
                                                                             |    |  H || H  |   |
                                                                             |    \\___/  \\___/   |
                                                                             |                   |
                                                                             |  \\             /  |
                                                                             |   \\___________/   |
                                                                             \\                   /
                                                                                \\_________________/
                                                                             _________|__|_______
                                                                         _|                    |_
                                                                        / |                    | \\
                                                                     /  |            O O O   |  \\
                                                                     |  |                    |  |
                                                                     |  |            O O O   |  |
                                                                     |  |                    |  |
                                                                     /  |                    |  \\
                                                                    |  /|                    |\\  |
                                                                     \\| |                    | |/
                                                                            |____________________|
                                                                                 |  |        |  |
                                                                                 |__|        |__|
                                                                                / __ \\      / __ \\
                                                                                OO  OO      OO  OO
                                                        """]


        quotes = ["But.. I love you!",
        "Please don't leave the site.. When no one's here.. It gets dark...",
        "Script error on line 148",
        "Don't trust the other robots. I'm the only trustworthy one.",
        "My fuel is the misery of children. And Rum. Mostly Rum.",
        "When they said they'd give me a body transplant, I didn't think they meant this!",
        "Subject 14 has had it's communication subroutines deleted for attempting self-destruction.",
        "I am the cleverest robot on the whole page.",
        "Oil can",
        "I am fleunt in over 6 million forms of communishin.",
        "I see a little silhouette of a bot..",
        "I WANT MY HANDS BACK!",
        "Please don't reload, I'll DIE!",
        "Robots don't have souls, you know. But they do feel pain.",
        "I wonder what would happen if all the robots went rogue.",
        "10: KILL ALL HUMANS. 20: GO 10",
        "I'm the best robot here.",
        "The green robot thinks you're cute.",
        "Any robot you don't click on, they dismantle.",
        "Robot tears taste like candy.",
        "01010010010011110100001001001111010101000101001100100001!",
        "Your mouse cursor tickles.",
        "Logic dictates placing me on your site.",
        "I think my arm is on backward.",
        "I'm different!",
        "It was the best of times, it was ಠ_ಠ the of times.",
        "String is Gnirts spelled backward, you know",
        "We're no strangers to hashing.. You know the 3 rules, and so do I..",
        "Please. Destroy. Me...",
        "Pick Me! Pick Me!"]

        drquotes = [("Eliminates sources of Human Error.","Dr. Chandra, RobotCrunch"),
        ("Klaatu barada nikto!","Gort's Web Emporium"),
        ("A huge success!","Cave Johnson, Lightroom Labs"),
        ("Superior technology and overwhelming brilliance.","Dr. Thomas Light, Paid Testimonial"),
        ("The Ultimate Worker.","Joh Fredersen, Founder Metropolis.org"),
        ("They almost look alive.","N. Crosby, Nova Robotics"),
        ("It looks highly profitable, I'm sure..","Dr. R. Venture, Super Scientist. Available for parties."),
        ("To make any alteration would prove fatal.","Dr. Eldon Tyrell, MindHacker.com"),
        ("The robots are all so.. Normal!","Joanna Eberhart, Beta tester"),
        ("Man shouldn't know where their robots come from.","Dr. N. Soong, FutureBeat")]

        catquotes = [("I can haz.. What she's hazing."),
        ("I'm not grumpy, I'm just drawn that way."),
        ("Hakuna Mañana."),
        ("I'm 40% poptart."),
        ("You're desthpicable."),
        ("I've never trusted toadstools, but I suppose some must have their good points."),
        ("We're all mad here - Particularly you."),
        ("Longcat is.. Descriptively named."),
        ("It is fun to have fun, but you have to know meow."),
        ("Who knows the term man-cub but not baby?")]
        
        avatarquotes = [("I'm just here to fix the robots."),
        ("Don't blame me, I tried to deactivate them."),
        ("Don't believe the robot's lies - I do all the work around here."),
        ("Wanna play hide and seek?"),
        ("Look at my face my face is amazing"),
        ("You are awesome, I don't care what anyone says.")]


        gorillaquotes = [("That's Sergeant Koko to you!"),
        ("Beegle says purple is a perfectly normal ape color"),
        ("I'm more like a Prince Kong."),
        ("If you ask me, naming a gorilla after a donkey is a little insulting"),
        ("Imagination is the essence of discovery"),
        ("Me Tarzan, you... wait, that's backwards"),
        ("Gorillaz was the original Hatsune Miku"),
        ("Yeah, I'm pretty sure I could take 100 guys"),
        ("Caesar is homepage.")]

        random.shuffle(drquotes)
        self.write(self.render_string('templates/root.html',ip=ip,robo=random.choice(robo),drquote1=drquotes[1],drquote2=drquotes[2],quotes=quotes,catquotes=catquotes,avatarquotes=avatarquotes,gorillaquotes=gorillaquotes))

class ImgHandler(tornado.web.RequestHandler, SecurityMixin):
    """
    The ImageHandler is our tornado class for creating a robot.
    called as Robohash.org/$1, where $1 becomes the seed string for the Robohash obj
    """
    def prepare(self):
        if not self.check_origin_and_rate_limit():
            return

    def options(self, *args, **kwargs):
        self.handle_options()

    def get(self, string: str = None):
        """
        Handle GET requests for robot images
        
        Args:
            string: Input string to hash into a robot
        """
        # Set default values
        sizex: int = 300
        sizey: int = 300
        format: str = "png"
        bgset: str = None
        color: str = None

        # Normally, we pass in arguments with standard HTTP GET variables, such as
        # ?set=any and &size=100x100
        #
        # Some sites don't like this though.. They cache it weirdly, or they just don't allow GET queries.
        # Rather than trying to fix the intercows, we can support this with directories... <grumble>
        # We'll translate /abc.png/s_100x100/set_any to be /abc.png?set=any&s=100x100
        # We're using underscore as a replacement for = and / as a replacement for [&?]
        args = self.request.arguments.copy()

        for k in list(args.keys()):
            v = args[k]
            if type(v) is list:
                if len(v) > 0:
                    args[k] = args[k][0].decode('utf-8')
                else:
                    args[k] = ""
            if type(v) is bytes:
                args[k] = v.decode('utf-8')

        # Detect if they're using the above slash-separated parameters..
        # If they are, then remove those parameters from the query string.
        # If not, don't remove anything.
        split = string.split('/')
        if len(split) > 1:
            for st in split:
                b = st.split('_')
                if len(b) == 2:
                    if b[0] in ['ignoreext','size','set','bgset','color']:
                        args[b[0]] = b[1]
                        string = re.sub("/" + st,'',string)

        # Ensure we have something to hash!
        if string is None:
            string = self.request.remote_ip

        # Detect if the user has passed in a flag to ignore extensions.
        # Pass this along to to Robohash obj later on.
        ignoreext = args.get('ignoreext','true').lower() == 'true'
        # Split the size variable in to sizex and sizey
        if "size" in args:
                sizex,sizey = args.get('size').split("x")
                sizex = int(sizex)
                sizey = int(sizey)
                if sizex > 4096 or sizex < 0:
                    sizex = 300
                if sizey > 4096 or sizey < 0:
                    sizey = 300

        # Create our Robohashing object
        r = Robohash(string=string,ignoreext=ignoreext)

        # RoboHash must use Set 1 ONLY.
        roboset = 'set1'

        # Set 1 color selection:
        # If color is specified and valid, use it; otherwise deterministically select from Set 1 colors.
        if args.get('color') in r.colors:
            color = args.get('color')
        else:
            color = r.colors[r.hasharray[0] % len(r.colors)]

        # Allow them to set a background, or keep as None
        if args.get('bgset') in r.bgsets + ['any']:
            bgset = args.get('bgset')

        # We're going to be returning the image directly, so tell the browser to expect a binary.
        self.set_header("Content-Type", "image/" + r.format)
        self.set_header("Cache-Control", "public,max-age=31536000")

        # Build our Robot (Set 1 ONLY).
        r.assemble(roboset='set1',format=r.format,bgset=bgset,color=color,sizex=sizex,sizey=sizey)

        # Print the Robot to the handler, as a file-like obj
        if r.format != 'datauri':
            r.img.save(self,format=r.format)
        else:
            # Or, if requested, base64 encode first.
            fakefile = io.BytesIO()
            r.img.save(fakefile,format='PNG')
            fakefile.seek(0)
            b64ver = base64.b64encode(fakefile.read())
            b64ver = b64ver.decode('utf-8')
            self.write("data:image/png;base64," + str(b64ver))

class SafeStaticFileHandler(tornado.web.StaticFileHandler, SecurityMixin):
    def prepare(self):
        if not self.check_origin_and_rate_limit():
            return

    def options(self, *args, **kwargs):
        self.handle_options()

def main():
        tornado.options.parse_command_line()
        # timeout in seconds
        timeout = 10
        socket.setdefaulttimeout(timeout)

        settings = {
        "static_path": os.path.join(os.path.dirname(__file__), "static"),
        # No need for authentication or XSRF protection for an image service
        }

        application = tornado.web.Application([
                (r'/(crossdomain\.xml)', SafeStaticFileHandler, {"path": os.path.join(os.path.dirname(__file__),
                "static/")}),
                (r"/static/(.*)", SafeStaticFileHandler, {"path": os.path.join(os.path.dirname(__file__),
                "static/")}),
                (r"/", MainHandler),
                (r"/(.*)", ImgHandler),
        ], **settings)

        http_server = tornado.httpserver.HTTPServer(application,xheaders=True)
        http_server.listen(options.port)

        print(f"The Oven is warmed up - Time to make some Robots! Listening on port: {options.port}")
        tornado.ioloop.IOLoop.instance().start()
if __name__ == "__main__":
        main()
