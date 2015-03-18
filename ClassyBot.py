import re
import random
from random import getrandbits
import os.path
import logging
import traceback

import socket
import time
from time import strftime
from datetime import timedelta
import threading

import urllib2
from bs4 import BeautifulSoup
import goslate

import Settings
from PhraseGetter import *
from games import HijackGame

FILE_ALERT = os.path.join(phraseDir, "Alerts.txt")
NUM_CHATTER = 15
NUM_TRIGGER = 18
NUM_RESPONSE = 19

logging.addLevelName(NUM_CHATTER, "CHATTER")
logging.addLevelName(NUM_TRIGGER, "TRIGGER")
logging.addLevelName(NUM_RESPONSE, "RESPONSE")

def chatter(self, message, *args, **kws):
    if self.isEnabledFor(NUM_CHATTER):
        self._log(NUM_CHATTER, message, args, **kws)

def trigger(self, message, *args, **kws):
    if self.isEnabledFor(NUM_TRIGGER):
        self._log(NUM_TRIGGER, message, args, **kws)

def response(self, message, *args, **kws):
    if self.isEnabledFor(NUM_RESPONSE):
        self._log(NUM_RESPONSE, message, args, **kws)


logging.Logger.chatter = chatter
logging.Logger.trigger = trigger
logging.Logger.response = response
logging.basicConfig(level="CHATTER", format="%(levelname)s:%(name)s (%(asctime)s)\t%(message)s", datefmt="%Y-%m-%d %H:%M:%S")


#### ---- IRC Stuff ---- ####
## -- Main IRC bot -- ##
class GreetBot(threading.Thread):
    password = ""
    data = ""
    owner = ""
    botNick = "MeatBot"
    userName = botNick
    
    def __init__ (self, host, port, channels, botNick, owner, password, idleChannels = None):
        self.init = Settings.Settings().keywords
        self.host = host
        self.port = port
        self.botNick = botNick
        self.userName = botNick
        self.owner = owner
        self.password = password
        
        self.channelInfo = {}


        for chan in channels:
            self.initChannel(chan)
        if idleChannels:
            for chan in idleChannels:
                self.channelInfo[chan.lower()]["wait"] = idleChannels[chan]["wait"]
                self.channelInfo[chan.lower()]["last"] = time.time()

        self.idleChannels = idleChannels
        self.realName = "\"{h}\" for help.".format(h=self.init["Commands"]["help"])
        self.hostName = botNick
        self.initChannel(self.botNick)
        self.lastMsg = {}
        self.isAlertUp = False

        ## Variables for whois/whowas info retrieval.
        self.whoNick = ""
        self.whoIdentity = ""
        self.whoIdle = ""
        self.whoServer = ""
        self.whoLoginDate = ""
        self.searchingWho = False
        self.whoArgs = []
        
        self.lastTime = time.time()
        self.dataThreads = []
        self.timeGotData = time.time()
        self.translator = goslate.Goslate()
        self.makeLoggers()

        self.readFiles()
        
        threading.Thread.__init__(self)

    def makeLoggers(self):
        self.consoleLogger = logging.getLogger(type(self).__name__ +" (Console)")
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logging.Formatter("%(levelname)s:\t%(message)s"))
        self.consoleLogger.addHandler(consoleHandler)
        
##        self.generalLogger = logging.getLogger(type(self).__name__)
##        generalHandler = logging.FileHandler(os.path.join(os.path.dirname(__file__), "Logs", "BotLog.log"))
##        generalHandler.setFormatter(logging.Formatter("%(levelname)s:%(name)s (%(asctime)s)\t%(message)s",
##                                                      "%Y-%m-%d %H:%M:%S"))
##        self.generalLogger.addHandler(generalHandler)
##        self.generalLogger.propagate = False

    def closeLogHandlers(self):
        for handler in self.consoleLogger.handlers:
            handler.close()
##        for handler in self.generalLogger.handlers:
##            handler.close()
        self.consoleLogger.handlers = []
##        self.generalLogger.handlers = []

    def readFiles(self):
        self.files = {"react": Reaction(),
                      "subject": Subject(),
                      "greet": Greeting(),
                      "gossip": Gossip(),
                      "idle": Idle(),
                      "link": Link(),
                      "meta": Meta(),
                      "user": User(),
                      "song": Song(),
                      "singalong": SingAlong(),
                      "recite": Recital(),
                      "help": HelpMe(),
                      "quote": Quote(),}

    def run(self):
        channels = [chan for chan in self.channelInfo]
        self.__init__(self.host, self.port, channels, self.botNick, self.owner, self.password, self.idleChannels)
        
        ## Try to connect to server.
        try:
            self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except:
            self.consoleLogger.error("Failed to create socket.")
            return

        remoteIP = socket.gethostbyname(self.host)
        print(remoteIP)

        self.irc.connect((remoteIP, self.port))
        nickMsg = "NICK {nick}\r\n".format(nick = self.botNick)
        userMsg = "USER {user} {hname} {host} :{rname}\r\n".format(user = self.userName,
                                                                   hname = self.hostName,
                                                                   host = self.host,
                                                                   rname = self.realName)
        self.irc.send(nickMsg)
        self.irc.send(userMsg)
        sendMsg = "PRIVMSG NICKSERV :GHOST {botnick} {pword}\r\n".format(botnick = self.botNick,
                                                                         pword = self.password)
        self.irc.send(sendMsg)

        while True:
            try:
                self.makeLoggers()
                
                self.dataThreads.append(threading.Thread(target=self.getData))
                if not self.dataThreads[len(self.dataThreads) - 1].is_alive():
                    self.dataThreads[len(self.dataThreads) - 1].start()
                    
                for t in self.dataThreads:
                    if not t.is_alive():
                        t.join()
                self.dataThreads = []

                self.closeLogHandlers()
                if 200 < time.time() - self.timeGotData:
                    ## 200+ seconds passed since last message. Try reconnecting.
                    self.run()
            except IOError as ex:
                print("IO Error encountered: {args}".format(args=str(ex.args)))
                self.closeLogHandlers()
            except socket.timeout:
                self.consoleLogger.error("The socket timed out, it seems. Trying a connection after 15 seconds.")
                time.sleep(15)
                
                ## Try again.
                self.run()
            finally:
                time.sleep(0.5)

    def act(self, data, channel, action):
        if "#" in channel:
            action = re.sub(self.init["Substitutions"]["channel"], channel, action, flags=re.I)
            if self.channelInfo[channel.lower()]["quiet"]:
                return
        if channel.lower() == self.botNick.lower():
            return
            
        ## The bot sends an action ("/me" message).
        sendMsg = "PRIVMSG {chan} :\001ACTION {act}\001\r\n".format(chan=channel, act=action)
        self.irc.send(sendMsg)
        
        prettyMsg = "\n[{time}]({chan}) * {bot} {acts}".format(time=strftime("%H:%M:%S"),
                                                               chan=channel,
                                                               bot=self.botNick,
                                                               acts=action)
        print(prettyMsg)

    def alert(self, message):
##        if not self.isAlertUp:
##            self.isAlertUp = True
        
##            self.isAlertUp = False
            
        return

    def askTime(self, server = ""):
        self.irc.send("TIME {s}\r\n".format(s = server))

    def checkKeywords(self, msg, nick, channel):
        keywords = DictInDict(FILE_ALERT, "keyword").keyValues
        caseMatters = False
        needsWhole = False
        isRegex = False
        found = False

        alerts = []
        newAlert = ""

        for kw in keywords:
            match = kw
            if "no" in keywords[kw]["case-sensitive"]:
                match = r"(?i){m}".format(m=match)
            else:
                match = keywords[kw]["keyword"]
                
            if "yes" in keywords[kw]["whole"]:
                match = r"\b{m}\b".format(m=match)

            if keywords[kw]["regex"]:
                match = r"{r}".format(r=keywords[kw]["regex"])

            match = re.compile(match)
            
            if match.search(msg):
                if keywords[kw]["react"]:
                    chance = 100
                    if keywords[kw]["chance"]:
                        try:
                            chance = float(keywords[kw]["chance"])
                        except ValueError:
                            pass

                    if random.randint(0,100) < chance:
                        reaction = self.subMsg(keywords[kw]["react"], nick, channel)
                        reaction = self.parseParens(self.parseBraces(reaction))
                        if "act" == keywords[kw]["mode"]:
                            self.act(msg, channel, reaction)
                        else:
                            self.say(msg, channel, reaction)

                        found = True

                if "no" != keywords[kw]["alert"]:
                    newAlert = "({chan})<{nick}> {msg} [{kw} mentioned]".format(chan=channel, nick=nick,
                                                                                msg=msg, kw=keywords[kw]["keyword"])
                    alerts.append(newAlert)

        if alerts:
            alertThread = threading.Thread(target=self.alert, args=(str("\n".join(alerts)),))
            alertThread.start()
        
        return found

    def disconnect(self, msg=":("):
        self.irc.send("QUIT :{msg}\r\n".format(msg=msg))

    def eightball(self, data, channel, nick, msgType):
        if self.channelInfo[channel]["recite"]:
            return

        self.channelInfo[channel]["recite"] = "eightball"
        self.act(data, channel, self.subMsg(random.choice(self.init["Choices"]["eightballprep"].split(self.init["Splitters"]["choices-eightball"])), nick, channel))
        time.sleep(2.5)
        remark = self.subMsg(random.choice(self.init["Choices"]["eightballremark"].split(self.init["Splitters"]["choices-eightball"])), nick, channel)
        if "*/*" in remark:
            self.act(data, channel, remark.replace("*/*", ""))
        else:
            self.say(data, channel, remark, msgType)
        time.sleep(1)
        self.say(data, channel, self.getMsg(nick, "react", "eightball", channel, True), msgType)
        self.channelInfo[channel]["recite"] = None
        
    def getData(self):
        self.init = Settings.Settings().keywords
        self.irc.setblocking(0)
        try:
            data = self.irc.recv(4096)
        except socket.error:
            return
        
        data = re.sub("\x03\d+", "", data)

        ## Set a timer for idle messages in each channel.
        ## If the channel is quiet for too long, the bot says something.
        for chan in self.channelInfo:
            if self.channelInfo[chan]["wait"]:
                if re.search(r"(?i):\S+ (PRIVMSG|NOTICE) {chan} :".format(chan = chan), data):
                    self.channelInfo[chan]["last"] = time.time()
                elif self.channelInfo[chan]["wait"] <= time.time() - self.channelInfo[chan]["last"]:
                    self.say(data, chan, self.getMsg(self.botNick, "idle", self.init["Headers"]["idle-talk"], chan, True))
                    self.channelInfo[chan]["last"] = time.time()

        data = re.split(r"(\r|\n|\r\n|\n\r)", data)
        
        for line in data:
            if line.strip():
                self.prettyOutput(line)
                self.timeGotData = time.time()
            dataProcess = threading.Thread(target=self.processData, args=(line,))
            dataProcess.start()

        return

    def getMsg(self, nick, classType, header, channel, capitalize = False):
        ## Get a random phrase from a class that reads a text file full of phrases.
        try:
            msg = self.files[classType].getPhrase(header)
        except ValueError:
            self.readFiles()
            msg = self.files[classType].getPhrase(header)
        
        
        ## Make sure the same phrase is not used more than once consecutively.
        if classType + header + channel in self.lastMsg:
            if 5 < len(self.lastMsg[classType + header + channel]):
                self.lastMsg[classType + header + channel].pop(0)
            while msg in self.lastMsg[classType + header + channel]:
                msg = self.files[classType].getPhrase(header)
        else:
            self.lastMsg[classType + header + channel] = []

        self.lastMsg[classType + header + channel].append(msg)

        msg = self.subMsg(msg, nick, channel, capitalize)

        return msg

    def getSubject(self, nick):
        initNick = nick
        nick = self.whoIs(nick)
        if not nick:
            nick = initNick

        subject = [initNick, User().randCallNick(nick)]
        for gen in self.files["user"].getGenders(nick):
            subject.append(self.files["subject"].getPhrase(gen))
        subject = random.choice(subject)
        subject = self.subMsg(subject, nick)

        self.whoClearData()
        
        return subject

    def ghost(self, nick, password):
        sendMsg = "PRIVMSG NICKSERV :GHOST {nick} {pword}\r\n".format(nick=nick, pword=password)
        self.irc.send(sendMsg)
        self.consoleLogger.info("(NickServ)<You> Smite this so-called \"{nick}\"".format(nick=nick))

    def initChannel(self, channel):
        self.channelInfo[channel.lower()] = {"users": [], "wait": None, "last": time.time(), "game": None, "singalong": None, "recite": None, "quiet": False, "pause": False}
            
    def join(self, data, nick, channel, msg = ""):
        if channel.lower() != self.botNick.lower() and "#" in channel:
            sendMsg = "JOIN {chan}\r\n".format(chan = channel)
            
            if channel.lower() not in self.channelInfo:
                self.initChannel(channel)

            self.irc.send(sendMsg)
            
            try:
                self.consoleLogger.info(sendMsg.strip())
            except AttributeError:
                self.prettyOutput(sendMsg)
            finally:       
                time.sleep(1)
                if msg:
                    self.say(data, channel, msg, "PRIVMSG")
                else:
                    if getrandbits(1):
                        self.say(data, channel, self.getMsg(nick, "react", self.init["Headers"]["reaction-jointalk"], channel, True))
                    else:
                        self.act(data, channel, self.getMsg(nick, "react", self.init["Headers"]["reaction-joinact"], channel))

        return

    def lookForCmd(self, data, nick):
        gotMsg = re.match(r"(?i):(\S+) (PRIVMSG|NOTICE) (#?\S+) :\s*(\S+)", data)

        if gotMsg and "nickserv" not in gotMsg.group(1).lower() and self.host.lower() not in gotMsg.group(1).lower():
            try:
                arg = data.split(gotMsg.group(0))[1].strip()
            except IndexError:
                arg = ""
            try:
                msg = data.split(" :")[1]
            except IndexError:
                msg = ""
            msgType = gotMsg.group(2)
            channel = gotMsg.group(3)
            cmd = gotMsg.group(4)

            arg = arg.decode("utf-8")
            msg = msg.decode("utf-8")

            if channel.lower() == self.botNick.lower():
                if self.botNick.lower() != nick.lower():
                    channel = nick
                else:
                    return
            if channel.lower() not in self.channelInfo:
                self.initChannel(channel)
            
            if self.channelInfo[channel.lower()]["recite"] and "eightball" != self.channelInfo[channel.lower()]["recite"]:
                if "4'33\"" == self.channelInfo[channel.lower()]["recite"].currentTitle:
                    if self.init["Commands"]["stoppoem"] == cmd.lower():
                        self.channelInfo[channel.lower()]["recite"] = None
                    else:
                        return
            if self.channelInfo[channel.lower()]["quiet"]:
                if self.init["Commands"]["quiet"] == cmd.lower() and channel.lower() != self.botNick.lower():
                    if "off" == arg.lower():
                        self.channelInfo[channel.lower()]["quiet"] = False
                        return
                else:
                    return
            if self.channelInfo[channel.lower()]["game"]:
                game = self.channelInfo[channel.lower()]["game"]
                if game.gameTitle == self.init["Titles"]["game-hijack"]:
                    output = game.processCommand(nick, msg, self.channelInfo[channel.lower()]["users"])
                    if output:
                        for tup in output:
                            if self.channelInfo[channel.lower()]["game"]:
                                self.say(data, channel, tup[0], msgType)
                                time.sleep(tup[1])
                            else:
                                break
                        return
            if self.init["Commands"]["hi"] == cmd.lower():
                if arg and self.botNick.lower() not in arg.lower():
                    subject = arg.strip(",.?:;!").strip()
                    mainNick = self.files["user"].getMainNick(subject)
                    if mainNick:
                        subject = self.getSubject(mainNick)
                else:
                    subject = self.getSubject(nick)
                self.say(data, channel, "{greet}, {subject}. {phrase}".format(greet = self.getMsg(nick, "greet", "greeting", channel, True),
                                                                        subject = subject,
                                                                        phrase = self.getMsg(nick, "greet", "phrase", channel, True)),
                         msgType)
            elif self.init["Commands"]["bye"] == cmd.lower():
                if arg and self.botNick.lower() not in arg.lower():
                    subject = arg.strip(",.?:;!").strip()
                    mainNick = self.files["user"].getMainNick(subject)
                    if mainNick:
                        subject = self.getSubject(mainNick)
                else:
                    subject = self.getSubject(nick)
                self.say(data, channel, "{bye}, {subject}".format(bye = self.getMsg(nick, "greet", "bye", channel, True),
                                                                  subject = subject), msgType)
            elif self.init["Commands"]["eightball"] == cmd.lower():
                self.eightball(data, channel, nick, msgType)
            elif self.init["Commands"]["help"] == cmd.lower():
                self.say(data, channel, HelpMe().getHelp(arg), msgType)
            elif self.init["Commands"]["link"] == cmd.lower():
                sendMsg = self.files["link"].getTrigger(arg)
                if list == type(sendMsg):
                    counter = 0
                    for link in sendMsg:
                        self.say("", nick, link, "NOTICE")
                        counter += 1

                        if counter > 4:
                            time.sleep(2)
                            counter = 0
                else:
                    self.say(data, nick, sendMsg, "NOTICE")
            elif self.init["Commands"]["lottery"] == cmd.lower():
                self.say(data, channel, random.choice(self.channelInfo[channel.lower()]["users"]), msgType)
            elif self.init["Commands"]["quiet"] == cmd.lower():
                self.channelInfo[channel.lower()]["quiet"] = True
            elif self.init["Commands"]["roll"] == cmd.lower():
                if re.match(r"\d+d\d+\b", arg):
                    dice = int(arg.split("d")[0])
                    sides = int(arg.split("d")[1])
                    if dice > 100:
                        dice = 100
                    if sides > 100:
                        sides = 100
                    numbers = []
                    try:
                        for _ in range(dice):
                            numbers.append(str(random.randint(1, sides)))
                    except ValueError:
                        self.say(data, channel, self.getMsg(nick, "meta", self.init["Headers"]["meta-rollinvalid"], channel, True), msgType)
                    numbers = ", ".join(numbers)
                    self.say(data, channel, numbers, msgType)
                else:
                    self.say(data, channel, self.init["Inform"]["howto-rolldice"], msgType)
            elif self.init["Commands"]["rockpaperscissors"] == cmd.lower():
                self.say(data, channel, random.choice(self.init["Choices"]["rockpaperscissors"].split(self.init["Splitters"]["choices-rps"])), msgType)
            elif self.init["Commands"]["sing"] == cmd.lower():
                if Song().getQuote(arg):
                    msg = Song().getQuote(arg)
                else:
                    msg = self.getMsg(nick, "meta", self.init["Headers"]["meta-nosong"], channel, True) +" (Try \"{g} {cat}\")".format(g=self.init["Commands"]["songlist"],
                                                                                                                                       cat=self.init["Arguments"]["songlist-cat"])
                self.say(data, channel, msg, msgType)
            elif self.init["Commands"]["singalong"] == cmd.lower():
                if not self.channelInfo[channel.lower()]["singalong"]:
                    if self.files["singalong"].getTitle(arg):
                        self.channelInfo[channel.lower()]["singalong"] = SingAlong()
                        songInstance = self.channelInfo[channel.lower()]["singalong"]
                        songTitle = songInstance.nextLine(arg)
                        self.say(data, channel, songTitle, msgType)
                    else:
                        if arg.strip():
                            msg = self.getMsg(nick, "meta", self.init["Headers"]["meta-nosong"], channel, True) +" (Try \"{g} {cat}\")".format(g=self.init["Commands"]["songlist"],
                                                                                                                                               cat=self.init["Arguments"]["songlist-cat"])
                        else:
                            msg = "(Try \"{g} {cat}\" to get songs categorized by movie and such)".format(g=self.init["Commands"]["songlist"],
                                                                                                          cat=self.init["Arguments"]["songlist-cat"])
                        self.say(data, channel, msg, msgType)
            elif self.init["Commands"]["songlist"] == cmd.lower():
                self.say(data, channel, self.files["singalong"].getLists(arg), msgType)
            elif self.init["Commands"]["startgame"] == cmd.lower():
                if arg:
                    startMsg = ""
                    if self.channelInfo[channel.lower()]["game"]:
                        gameMsg = self.init["Inform"]["gamealreadystarted"]
                        gameMsg = gameMsg.replace(self.init["Substitutions"]["game"], self.channelInfo[channel.lower()]["game"].gameTitle)
                        self.say(data, channel, gameMsg, msgType)
                    elif arg.lower() == self.init["Arguments"]["startgame-hijack"]:
                        self.channelInfo[channel.lower()]["game"] = HijackGame()
                        startMsg = self.init["Inform"]["startgame-hijack"]
                    if startMsg:
                        self.say(data, channel, startMsg, msgType)
                else:
                    self.say(data, channel, self.init["Inform"]["howto-startgame"], msgType)
            elif self.init["Commands"]["stopgame"] == cmd.lower():
                if self.channelInfo[channel.lower()]["game"]:
                    self.say(data, channel, "Stopping {g}.".format(g=self.channelInfo[channel.lower()]["game"].gameTitle), msgType)
                    self.channelInfo[channel.lower()]["game"] = None
                else:
                    self.say(data, channel, self.init["Inform"]["nogame"], msgType)
            elif self.init["Commands"]["stopsong"] == cmd.lower():
                if self.channelInfo[channel.lower()]["singalong"]:
                    self.channelInfo[channel.lower()]["singalong"] = None
                    self.act(data, channel, self.getMsg(nick, "meta", self.init["Headers"]["meta-songstopact"], channel))
            elif self.init["Commands"]["poem"] == cmd.lower():
                if not self.channelInfo[channel.lower()]["recite"]:
                    self.channelInfo[channel.lower()]["recite"] = Recital()
                    piece = self.channelInfo[channel.lower()]["recite"]
                    if piece.getTitle(arg):
                        piece.currentTitle = piece.getTitle(arg)
                    else:
                        if arg:
                            self.say(data, channel, "Try \"{g}\".".format(g=self.init["Commands"]["poemlist"]))
                            return
                        else:
                            titles = []
                            for t in piece.byTitle:
                                titles.append(t)
                            piece.currentTitle = random.choice(titles)
                    piece.lenTitle = len(piece.byTitle[piece.currentTitle])
                    reciteThread = threading.Thread(target=self.recite, args=(channel.lower(),))
                    reciteThread.start()
            elif self.init["Commands"]["poemlist"] == cmd.lower():
                self.say(data, channel, self.files["recite"].getLists(arg), msgType)
            elif self.init["Commands"]["quote"] == cmd.lower():
                self.say(data, channel, self.files["quote"].getQuote(arg), msgType)
            elif self.init["Commands"]["quotecat"] == cmd.lower():
                self.say(data, channel, self.files["quote"].getCategories(arg), msgType)
            elif self.init["Commands"]["stoppoem"] == cmd.lower():
                if self.channelInfo[channel.lower()]["recite"]:
                    self.channelInfo[channel.lower()]["recite"] = None
                    self.act(data, channel, self.getMsg(nick, "meta", self.init["Headers"]["meta-songstopact"], channel))
            elif self.init["Commands"]["translate"] == cmd.lower():
                if arg:
                    tFrom = re.search(r"\bfrom=(\w+(-\w)*)", arg, re.I)
                    tTo = re.search(r"\bto=(\w+(-\w)*)", arg, re.I)

                    arg = arg.encode("utf-8")

                    try:
                        arg = arg.replace(tFrom.group(), "")
                        tFrom = tFrom.group(1)
                    except (AttributeError, ValueError):
                        tFrom = ""

                    try:
                        arg = arg.replace(tTo.group(), "")
                        tTo = tTo.group(1)
                    except (AttributeError, ValueError):
                        tTo = "en"

                    tFrom = re.sub(r"\W+", "-", tFrom)
                    tFrom = re.sub(r"\W+$", "", tFrom).strip()
                    tTo = re.sub(r"\W+", "-", tTo)
                    tTo = re.sub(r"\W+$", "", tTo).strip()

                    if tFrom.lower() in self.init["Translate"]:
                        tFrom = self.init["Translate"][tFrom.lower()]
                    elif tFrom.lower() in self.init["Translate"].values():
                        tFrom = tFrom.lower()
                    else:
                        tFrom = ""

                    if tTo.lower() in self.init["Translate"]:
                        tTo = self.init["Translate"][tTo.lower()]
                    elif tTo.lower() in self.init["Translate"].values():
                        tTo = tTo.lower()
                    else:
                        tTo = "en"

                    translation = self.translator.translate(arg, tTo, tFrom)
                    
                    inLang = ""
                    outLang = "english"
                    try:
                        inLang = [l for l in self.init["Translate"] if self.translator.detect(arg).lower() == self.init["Translate"][l]][0]
                        outLang = [l for l in self.init["Translate"] if tTo == self.init["Translate"][l]][0]
                    except IndexError:
                        print(self.translator.detect(arg).lower())

                    self.say(data, channel, "{trans} [{fr} > {to}]".format(fr=inLang, to=outLang, trans=translation.encode("utf-8")))
                    
            elif self.channelInfo[channel.lower()]["singalong"]:
                songInstance = self.channelInfo[channel.lower()]["singalong"]
                if songInstance.currentTitle:
                    if self.channelInfo[channel.lower()]["pause"]:
                        if self.init["Commands"]["unpause"] == cmd.lower():
                            self.channelInfo[channel.lower()]["pause"] = False
                            self.say(data, channel, "Resuming \"{}\" singalong.".format(songInstance.currentTitle))
                        return
                    elif self.init["Commands"]["pause"] == cmd.lower():
                        self.channelInfo[channel.lower()]["pause"] = True
                        self.say(data, channel, "Song paused. \"{}\" to continue.".format(self.init["Commands"]["unpause"]))
                        return
                    elif songInstance.currentQ == songInstance.byTitle[songInstance.currentTitle][songInstance.lenTitle] and songInstance.currentOrder >= songInstance.lenTitle:
                        self.channelInfo[channel.lower()]["singalong"] = None
                        self.act(data, channel, self.getMsg(nick, "meta", self.init["Headers"]["meta-songstopact"], channel) +" (Song finished)")
                        return
                    else:
                        if self.init["Commands"]["nextlyric"] == cmd.lower():
                            songLine = songInstance.autoNext()
                        else:
                            songLine = songInstance.nextLine(msg)
                            
                        if songLine:
                            self.say(data, channel, songLine, msgType)
                        if songInstance.currentQ == songInstance.byTitle[songInstance.currentTitle][songInstance.lenTitle] and songInstance.currentOrder >= songInstance.lenTitle:
                            self.channelInfo[channel.lower()]["singalong"] = None
                            self.act(data, channel, self.getMsg(nick, "meta", self.init["Headers"]["meta-songdoneact"], channel) +" (Song finished)")
            elif cmd.lower() in self.init["SpecialCommands"].values():
                self.whoIs(nick)
                if self.whoIdentity.lower() == self.owner.lower():
                    if self.init["SpecialCommands"]["act"] == cmd.lower():
                        try:
                            actChan = arg.split(" ")[0]
                            sendMsg = arg[arg.index(actChan) + len(actChan):].strip()

                            self.act(data, actChan, sendMsg)
                        except IndexError:
                            self.say(data, nick, "To have me act out something, type \"!act [channel/person] [action].\"", "NOTICE")
                        
                    elif self.init["SpecialCommands"]["join"] == cmd.lower():
                        try:
                            joinChan = arg.split(" ")[0]
                            sendMsg = arg[arg.index(joinChan) + len(joinChan):].strip()

                            self.join(data, joinChan, joinChan, sendMsg)
                        except IndexError:
                            self.say(data, nick, "To have me join a channel, type \"!join #[channel] [optional entry message].\"", "NOTICE")
                        
                    elif self.init["SpecialCommands"]["nickchange"] == cmd.lower():
                        self.nickChange(arg)
                    elif self.init["SpecialCommands"]["part"] == cmd.lower():
                        try:
                            partChan = arg.split(" ")[0]
                            sendMsg = arg[arg.index(partChan) + len(partChan):].strip()

                            self.part(partChan, sendMsg)
                        except IndexError:
                            self.say(data, nick, "To boot me from a channel, type \"!part #[channel] [optional exit message].\"", "NOTICE")
                        
                    elif self.init["SpecialCommands"]["quit"] == cmd.lower():
                        try:
                            quitMsg = arg
                            self.disconnect(quitMsg)
                        except IndexError:
                            self.say(data, nick, "To have me gone, type \"!quit [optional exit message]\"", "NOTICE")
                        
                    elif self.init["SpecialCommands"]["say"] == cmd.lower():
                        try:
                            sayChan = arg.split(" ")[0]
                            sendMsg = arg[arg.index(sayChan) + len(sayChan):].strip()

                            self.say(data, sayChan, sendMsg)
                        except IndexError:
                            self.say(data, nick, "To say something, type \"!say [channel/person] [message].\"", "NOTICE")
                        
                    
                    elif self.init["SpecialCommands"]["update"] == cmd.lower():
                        self.readFiles()
                        self.say(data, nick, "Updated.", "NOTICE")
                else:
                    self.say(data, nick, "Don't tell me what to do.", "NOTICE")
            else:
                isOrdinaryPm = True

                triggers = "|".join([r"({t}\b)".format(t=t).replace(".", "\.") for t in self.files["link"].keyValues])
                tMatches = [(m.span(), m.group()) for m in re.finditer(triggers, msg, re.I)]
    
                for m in tMatches:
                    self.say("", channel, self.files["link"].keyValues[m[1].lower()]["link"])


                lMatches = [m.group() for m in re.finditer(r"https?://\S+", msg)]
                for m in lMatches:
                    try:
                        response = urllib2.urlopen(m)
                        html = response.read()

                        soup = BeautifulSoup(html)
                        siteTitle = soup.title.string.encode("utf-8").strip()

                        if "YouTube" in siteTitle:
                            ## Get video time.
                            try:
                                for s in soup.find_all("script"):
                                    seconds = re.search(r"\Wlength_seconds\W+(\d+)\W", str(s))

                                    if seconds:
                                        seconds = int(seconds.group(1)) - 1
                                        siteTitle = " ".join([siteTitle, "[{}]".format(timedelta(seconds=seconds))])
                                        break
                            except TypeError:
                                pass

                        self.say("", channel, siteTitle)
                    except urllib2.URLError:
                        pass

                if tMatches or lMatches:
                    isOrdinaryPm = False
            
                if isOrdinaryPm:
                    if self.checkKeywords(msg, nick, channel):
                        return
                    
                    if "\001ACTION" == cmd and self.botNick.lower() in msg.lower(): 
                        self.act(data, channel, self.getMsg(nick, "react", self.init["Headers"]["reaction-nickact"], channel))
                    elif nick.lower() == channel.lower():
                        self.say(data, channel, self.getMsg(nick, "react", self.init["Headers"]["reaction-privtalk"], channel, True), msgType)
                    elif self.botNick.lower() in msg.lower() and "\001ACTION" not in msg.lower():
                        self.say(data, channel, self.getMsg(nick, "react", self.init["Headers"]["reaction-nicktalk"], channel, True), msgType)
       
        return
                
    def mode(self, channel, modeChar="", nick=""):
        sendMsg = "MODE {chan} {m} {nick}\r\n".format(chan=channel, m=modeChar, nick=nick)
        self.irc.send(sendMsg)
        self.consoleLogger.info(sendMsg.strip())
        
    def nickChange(self, nick):
        sendMsg = "NICK {nick}\r\n".format(nick=nick)
        self.irc.send(sendMsg)
        self.consoleLogger.info("You are now {nick}.".format(nick=nick))
        self.botNick = nick

    def parseBraces(self, stringName):
        choice = ""
        openIndex = 0
        closeIndex = 0

        openChar = self.init["Blocks"]["openomit"]
        closeChar = self.init["Blocks"]["closeomit"]

        openIndex = stringName.rfind(openChar)
        while closeIndex <= openIndex:
            closeIndex = stringName.find(closeChar, closeIndex + 1)
            
        tmpBlock = stringName[openIndex:closeIndex + 1]
        logging.debug("Method parseBraces: tmpBlock = {tmp}".format(tmp = tmpBlock))
        if getrandbits(1):
            stringName = stringName.replace(tmpBlock, "")
        else:
            stringName = stringName.replace(tmpBlock, tmpBlock.replace(openChar, "").replace(closeChar, ""))

        if openChar in stringName and closeChar in stringName:
            return self.parseBraces(stringName)

        return stringName.replace(openChar, "").replace(closeChar, "")

    def parseParens(self, stringName):
        choice = ""
        openIndex = 0
        closeIndex = 0

        openChar = self.init["Blocks"]["openchoose"]
        closeChar = self.init["Blocks"]["closechoose"]

        openIndex = stringName.rfind(openChar)
        while closeIndex <= openIndex:
            closeIndex = stringName.find(closeChar, closeIndex + 1)
            
        tmpBlock = stringName[openIndex:closeIndex + 1]
        stringName = stringName.replace(tmpBlock, random.choice(tmpBlock.replace(openChar, "").replace(closeChar, "").split(self.init["Splitters"]["parseoptions"])))

        if openChar in stringName and closeChar in stringName:
            return self.parseParens(stringName)

        return stringName.replace(openChar, "").replace(closeChar, "")

    def part(self, channel, msg):
        try:
            del self.channelInfo[channel.lower()]
            if "" == msg:
                msg = "I don't know why I'm leaving. :("
            sendMsg = "PART {chan} :{msg}\r\n".format(chan=channel, msg=msg)
            self.irc.send(sendMsg)
            self.consoleLogger.info("You left {chan}. ({msg})".format(chan=channel, msg=msg))
        except KeyError:
            pass

    def prettyOutput(self, line):
        line = line.strip()
        joined = re.match(r":(\S+)!\S+ JOIN (#\S+)$", line)
        kicked = re.match(r":(\S+)!\S+ KICK (#\S+) (\S+) :(.+)", line)
        parted = re.match(r":(\S+)!\S+ PART (#\S+)", line)
        quitted = re.match(r":(\S+)!\S+ QUIT(.*)", line)
        msged = re.match(r":(\S+)!\S+ PRIVMSG (\S+) :(.+)", line)
        nickChanged = re.match(r":(\S+)!\S+ NICK :(\S+)", line)
        noticed = re.match(r":(\S+)!\S+ NOTICE (\S+) :(.+)", line)
        
        if joined:
            joinNick = joined.group(1)
            chan = joined.group(2)
            line = "\t{nick} joined {chan}.".format(nick=joinNick,
                                                    chan=chan)
            
            self.channelInfo[chan.lower()]["users"].append(joinNick)

            # Greet the user if user is not the bot.
            if self.botNick.lower() != joinNick.lower() and "#" in chan:
                if bool(random.getrandbits(1)):
                    subject = self.getSubject(joinNick)
                    self.say(line, chan, "{hi}, {subject}. {phrase}".format(hi=self.getMsg(joinNick, "greet", "greeting", chan.lower(), True),
                                                                            subject=subject,
                                                                            phrase=self.getMsg(joinNick, "greet", "phrase", chan.lower(), True)))
                else:
                    self.say(line, chan, self.getMsg(joinNick, "greet", self.init["Headers"]["greeting-hiwhole"], chan.lower(), True))
        elif kicked:
            kicker = kicked.group(1)
            chan = kicked.group(2)
            kickedNick = kicked.group(3)
            kickMsg = kicked.group(4)
            
            line = "{kicker} kicked {kickee} out of {room}. ({reason})".format(kicker=kicker, kickee=kickedNick,
                                                                               room=chan, reason=kickMsg,)
            self.channelInfo[chan.lower()]["users"].remove(kickedNick)

            if self.botNick.lower() == kickedNick.lower():
                del self.channelInfo[chan.lower()]
                
        elif parted:
            quitNick = parted.group(1)
            chan = parted.group(2)
            line = "\t{nick} left {chan}.".format(nick=quitNick,
                                                  chan=chan)
            
            if self.channelInfo[chan.lower()]["game"]:
                game = self.channelInfo[chan.lower()]["game"]
                try:
                    if quitNick.lower() in game.players:
                        game.removePlayer(quitNick.lower())
                except AttributeError:
                    pass
            if quitNick in self.channelInfo[chan.lower()]["users"]:
                self.channelInfo[chan.lower()]["users"].remove(quitNick)

            # Gossip.
            if "#" in chan:
                self.say(line, chan, self.getMsg(quitNick, "gossip", "gossip", chan.lower(), True))
                
        elif quitted:
            quitNick = quitted.group(1)
            line = "\t{nick} quit. ({reason})".format(nick=quitNick,
                                                      reason=quitted.group(2).lstrip(" :"))
            for chan in self.channelInfo:
                if self.channelInfo[chan]["game"]:
                    game = self.channelInfo[chan]["game"]
                    try:
                        if quitNick.lower() in game.players:
                            game.removePlayer(quitNick.lower())
                    except AttributeError:
                        pass
                if quitNick in self.channelInfo[chan]["users"]:
                    self.channelInfo[chan]["users"].remove(quitNick)
                    self.say(line, chan, self.getMsg(quitNick, "gossip", "gossip", chan, True))
        elif msged:
            msg = msged.group(3).strip()
            line = "({chan})<{nick}> {msg}".format(chan=msged.group(2),
                                                   nick=msged.group(1),
                                                   msg=msg)
            if "\001ACTION " in msg:
                msg = msg.replace("\001ACTION", "")
                line = "({chan}) * {nick} {acts}".format(chan=msged.group(2),
                                                         nick=msged.group(1),
                                                         acts=msg.strip())
        elif nickChanged:
            oldNick = nickChanged.group(1)
            newNick = nickChanged.group(2)
            line = " * {oldnick} is now known as {newnick}.".format(oldnick=oldNick,
                                                                    newnick=newNick)
            for chan in self.channelInfo:
                if oldNick in self.channelInfo[chan]["users"]:
                    self.channelInfo[chan]["users"][self.channelInfo[chan]["users"].index(oldNick)] = newNick
                if self.channelInfo[chan]["game"]:
                    game = self.channelInfo[chan]["game"]
                    try:
                        if oldNick.lower() in game.players:
                            game.players[newNick.lower()] = game.players[oldNick.lower()]
                            game.players[newNick.lower()].name = newNick
                            del game.players[oldNick.lower()]
                    except AttributeError:
                        pass
        elif noticed:
            line = "({chan}) {nick} whispers: {msg}".format(chan=noticed.group(2),
                                                            nick=noticed.group(1),
                                                            msg=noticed.group(3))

        print("[{time}] {line}".format(time=strftime("%H:%M:%S"), line=line))

    def processData(self, data):
        try:
            nick = data.split("!")[0].translate(None, ":")
        except AttributeError:
            pass

        ## Respond to server pings:
        if "PING" in data.split(" ")[0]:
            pongMsg = "PONG {reply}\r\n".format(reply=data.split("PING ")[1])
            self.irc.send(pongMsg)
            print("[{time}] {pong}".format(time=strftime("%H:%M:%S"), pong=pongMsg))

        ## Join channels after the message of the day is out.
        if re.match(r"(?i):\S+ \d+ {bot}.* :End of /MOTD".format(bot=self.botNick.lower()), data.lower()):
            sendMsg = "PRIVMSG NICKSERV :IDENTIFY {own} {pword}\r\n".format(own=self.owner, pword=self.password)
            self.irc.send(sendMsg)
            print("(NickServ)<You> I am totally {own}. Seriously.".format(own=self.owner))

            sendMsg = "MODE {bot} +R\r\n".format(bot=self.botNick)
            self.irc.send(sendMsg)
            print(sendMsg.strip())
            for chan in self.channelInfo:
                joinThread = threading.Thread(target=self.join, args=(data, nick, chan))
                joinThread.start()

        ## Ghost any past copies of the bot already inside.
        nickUsed = re.match(r"(?i):\S+ \d+ \S+ (\w+) :Nickname is already in use", data)
        if nickUsed:
            self.nickChange("{nick}_".format(nick=nickUsed.group(1)))
            self.ghost(self.botNick, self.password)
            
        if re.match(r"(?i):\S+ NOTICE \S+ :.?\S+.? (is not online|has been ghosted)", data.lower()):
            self.nickChange(self.botNick)

        ## Get channel and user prefixes that represent modes (opped, voiced, moderated, etc.).
        gotChanPrefixes = re.match(r"(?i):.+{bot} .+ PREFIX=\(\w+\)(\S+) .+:are supported by this server".format(bot = self.botNick.lower()),
                                   data.lower())
        if gotChanPrefixes:
            self.chanPrefixes = gotChanPrefixes.group(1)
        else:
            self.chanPrefixes = "@+"

        showedNames = re.match(r"(?i):\S+ \d+ {bot}.? \S (#\S+) :".format(bot = self.botNick), data)
        if showedNames:
            channel = showedNames.group(1)
            users = data.split(showedNames.group(0))[1].translate(None, self.chanPrefixes)
            self.channelInfo[channel.lower()]["users"] = users.split(" ")
            self.consoleLogger.info(self.channelInfo[channel.lower()]["users"])

        ## Set a timer for idle messages in each channel.
        ## If the channel is quiet for too long, the bot says something.
        for chan in self.channelInfo:
            if self.channelInfo[chan]["wait"]:
                if "privmsg {chan} :".format(chan = chan.lower()) in data.lower():
                    self.channelInfo[chan]["last"] = time.time()
                else:
                    if self.channelInfo[chan]["wait"] <= time.time() - self.channelInfo[chan]["last"]:
                        self.say(data, chan, self.getMsg(nick, "idle", "say", chan, True))
                        self.channelInfo[chan]["last"] = time.time()
        
        whoIdMatch = re.match(r"(?i):\S+ \d+ {bot}.? (\S+) (\S+) :(wa|i)s logged in as".format(bot = self.botNick), data)
        whoIdleMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ (\d+ \d+) :second".format(bot = self.botNick), data)
        whoDateMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ (\S+) :(\S+ \S+ \d+ \d+:\d+:\d+ \d+)".format(bot = self.botNick), data)
        whoServerMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ (\S+\.\S+((\.\S+)+)?) :".format(bot = self.botNick), data)
        endWhoMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ :End of (/WHOIS list|WHOWAS)".format(bot = self.botNick.lower()), data.lower())

        if whoIdMatch:
            self.whoNick = whoIdMatch.group(1)
            self.whoIdentity = whoIdMatch.group(2)
        if whoIdleMatch:
            self.whoIdle = whoIdleMatch.group(1)
        if whoDateMatch:
            self.whoServer = whoDateMatch.group(1)
            self.whoLoginDate = whoDateMatch.group(2)
        if whoServerMatch:
            self.whoServer = whoServerMatch.group(1)
        if endWhoMatch:
            self.searchingWho = False

        inviteMatch = re.match(r"(?i):\S+ INVITE {bot}.? :(#\S+)".format(bot = self.botNick.lower()), data.lower())
        if inviteMatch:
            self.join(data, nick, inviteMatch.group(1))

       ## Respond to certain kinds of user input:
        checkCmd = threading.Thread(target=self.lookForCmd, args=(data, nick))
        checkCmd.start()

        return

    def recite(self, channel):
        while self.channelInfo[channel]["recite"]:
            piece = self.channelInfo[channel]["recite"]
            if piece.currentOrder > 0 and piece.currentOrder > piece.lenTitle:
                self.channelInfo[channel]["recite"] = None
                self.act("", channel, self.getMsg("", "meta", self.init["Headers"]["meta-recitaldoneact"], channel))
            else:
                if self.channelInfo[channel]["quiet"]:
                    pass
                else:
                    self.say("", channel, piece.autoNext())
                    time.sleep(piece.delay)
                            
        return
                
    def say(self, data, channel, msg, msgType="PRIVMSG"):
        ## Send a message to a channel or user. (channel = channel OR user)
        if "#" in channel:
            msg = re.sub(self.init["Substitutions"]["channel"], channel, msg, flags=re.I)
            if self.channelInfo[channel.lower()]["quiet"]:
                return
        if channel.lower() == self.botNick.lower():
            return

        counter = 0
        while msg:
            sendMsg = "{msgType} {chan} :{msg}\r\n".format(msgType = msgType.upper(), chan = channel, msg = msg[:300])
            self.irc.send(sendMsg)
            
            prettyMsg = "[{time}]({chan})<{bot}> {msg}".format(time=strftime("%H:%M:%S"),
                                                                               chan=channel,
                                                                               bot=self.botNick,
                                                                               msg=msg[:300])    
            print(prettyMsg)
            msg = msg[300:]
            counter += 1

            if counter >= 5:
                time.sleep(1)
                counter = 0

    def subMsg(self, msg, nick, channel="this place", capitalize=False):
        ## Substitute placeholders with meaningful values.
        msg = msg.replace(self.init["Substitutions"]["sendnick"], nick)
        msg = msg.replace(self.init["Substitutions"]["botnick"], self.botNick)
        msg = msg.replace(self.init["Substitutions"]["subjectplural"], self.files["subject"].getPhrase("plural"))
        msg = msg.replace(self.init["Substitutions"]["owner"], self.owner)
        msg = msg.replace(self.init["Substitutions"]["channel"], channel)

        ## Capitalize first /letter/.
        if capitalize:
            firstLetter = re.search("\w", msg).group(0)
            msg = msg[0:msg.index(firstLetter)] + firstLetter.upper() + msg[msg.index(firstLetter) + 1:]

        ## Replace "a" with "an" when necessary.
        for m in ["hour", "heir", "homage", "honest", "[aeiou]"]:
            anMatch = re.findall(r"(?i)\ba\s+{m}".format(m = m), msg)
            for m in anMatch:
                msg = msg[0:msg.index(m) + 1] +"n"+ msg[msg.index(m) + 1:]
                
        return msg

    def whoIs(self, nick, server = ""):
        self.irc.send("WHOIS {s} {nick}\r\n".format(s = server, nick = nick))
        self.searchingWho = True
        while self.searchingWho:
            pass

    def whoWas(self, nick, server = ""):
        self.irc.send("WHOWAS {s} {nick}\r\n".format(s = server, nick = nick))
        self.whoSearching = True
        while self.searchingWho:
            pass

    def whoClearData(self):
        self.whoNick = ""
        self.whoIdentity = ""
        self.whoIdle = ""
        self.whoServer = ""
        self.whoLoginDate = ""
        self.whoArgs = []

