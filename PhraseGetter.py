import re
import random
from random import getrandbits
import os.path
import logging
import traceback
import ConfigParser
from string import maketrans

import Settings

phraseDir = os.path.join(os.path.dirname(__file__), "database")
logDir = os.path.join(os.path.dirname(__file__), "log")

class Reaction(object):
    sendNick = ""
    ignore = "~`@\\"
    header = {}
    
    columns = {}
    
    def __init__(self, inputFile = os.path.join(phraseDir, "Reactions.txt")):
        self.inputFile = inputFile
        self.settingsFile = os.path.join(phraseDir, "Settings.ini")

        self.parseCalled = 0
        self.index = 0
        self.field = ""
        self.init = Settings.Settings().keywords
        self.logger = None

        self.readFile()

    def makeLogger(self):
        logging.basicConfig(level=logging.WARNING)
        self.logger = logging.getLogger(type(self).__name__)
        loggerHandler = logging.FileHandler(os.path.join(logDir, "PhraseRetrieval.log"))
        loggerHandler.setFormatter = logging.Formatter("%(levelname)s:%(name)s (%(asctime)s)\t%(message)s",
                                                       "%Y-%m-%d %H:%M:%S")
        self.logger.addHandler(loggerHandler)
        self.logger.propagate = False

    def closeLogHandlers(self):
        for handler in self.logger.handlers:
            handler.close()
        self.logger.handlers = []

    def readFile(self):
        self.init = Settings.Settings().keywords
        try:
            if os.path.isfile(self.inputFile):
                with open(self.inputFile, "r") as fileHandler:
                    lineNum = 0
                    
                    for line in fileHandler:
                        lineNum += 1
                        line = line.split(self.init["Splitters"]["field"])
                        for field in line:
                            self.field = field.strip()
                            if 1 == lineNum:
                                self.header[self.field] = self.index
                                self.columns[self.field] = []
                            else:
                                for col in self.columns:
                                    self.checkField(col, self.columns[col])
                            self.index += 1
                        self.index = 0
            else:
                self.logger.error("{f} does not exist.".format(f = self.inputFile))
        except IOError as ex:
            self.logger.error("IO Error encountered: {args}".format(args = str(ex.args)))

    def dumbDown(self, line):
        """ Simple way to "dumb" a string down to make matching less strict. """
        while re.search(r"[ .!?,-]$", line):
            line = line.rstrip(" ,.!?-")
        line = line.strip()
        line = re.sub(r"\W", "", line.replace(" ", "_"))
        while "__" in line:
            line = line.replace("__", "_").strip("_ ")
            
        return line

    def dumbRegex(self, line, willCompile=True):
        """ Makes matching a line to be much more permissive. """
        """ Returns a regex object. """
        ## Characters that might be draaaawnnn ouuut:
        ## "w" is handled separately to avoid conflict with "\W*" and "\w".
        mightDrawOut = "aeghilmnorsuyz"
            
        ## Remove extra spaces.
        while "  " in line:
            line = line.replace("  ", " ")

        line = line.rstrip(" .!?,-")
        line = line.strip()

        ## Spacing and punctuation shouldn't matter.
        line = re.sub(r"[^\w'\\-]+", "\W*", line)

        for f in re.finditer(r"'\w", line):
            re.sub(f.group(), r"'?{}".format(f.group()), line)

        ## Example: "running" could be "running", "runnin'", or "runnin"
        line = re.sub(r"(?i)\Bg+|'\b", "(g|')?", line)

        ## Either kind of OK works.
        line = re.sub(r"(?i)\bo+k\b", "okay", line)
        line = re.sub(r"(?i)\bo+ka+y+\b", "ok(ay)?", line)

        ## Several kinds of "whoa" work.
        line = re.sub(r"(?i)\b(whoah*|woah*|wh*ooh*)\b", "(whoah*|woah*|wh*ooh*)", line)

        ## Ha or hah.
        line = re.sub(r"(?i)\bhah*\b", "hah*", line)

        ## Kinds of "because".
        line = re.sub(r"(?i)\b(cause|cuz|because)\b", "(cause|cuz|because)", line)

        ## "Wanna" and "gonna" could be "want to" and "going to", and vice versa.
        line = re.sub(r"(?i)\b(wa+n+a+|wa+n+t\\W\*to+)\b", "(wanna|want\W*to)", line)
        line = re.sub(r"(?i)\b(go+n+a+|go+i+n+\(g+\|'\)\?\\W\*to)\b", "(gonna|goin(g|')?\W*to)", line)

        ## Optional "u" after "o" and before "r".
        ## Example: "colour" or "color" will both match.
        line = re.sub(r"(?i)\Bo+u*r+(\\W\*|$)", "o(u-?)*r\W*", line)
        
        ## Allow for optional drawn-out phrases.
        ## Example: "Yay" and "Yaaaaayyy" will both match.
        for char in mightDrawOut:
            line = re.sub(r"(?i)({c}(?!\*)(?!-\?)-?)+".format(c=char), "({c}-?)+".format(c=char), line)
        line = re.sub(r"(?<=[^\\])(w-?)+", "(w-?)+", line)
        
        ## Case won't matter.
        line = "(?i){l}".format(l=line)

        if willCompile:
            return re.compile(line)
        else:
            return line
    
    def getPhrase(self, phrase, capitalize = False):
        noHeader = True
        
        for col in self.columns:
            if phrase in col:
                phrase = col
                phrase = self.getField(phrase, self.columns[phrase])
                if capitalize:
                    phrase = phrase.replace(re.search("\w", phrase).group(0), re.search("\w", phrase).group(0).upper())

                phrase = phrase.strip()
                noHeader = False
                break
        if noHeader:
            self.logger.warning("Did not see a header that matched \"{header}\"".format(header = phrase))
        
        return phrase
    
    def checkField(self, headerItem, listName):
        try:
            if self.index == self.header[headerItem]:
                self.field = self.field.strip()
                self.field = self.field.translate(None, self.ignore)
                if re.search("\w+", self.field):
                    if self.field in listName:
                        pass
                    else:
                        listName.append(self.field)
        except LookupError:
            msg = ""
            tracebackInfo = traceback.format_exc().split("\n")
            for line in tracebackInfo:
                if line.strip():
                    msg = msg +"\n  "+ line

    def getField(self, stringName, listName):
        stringName = listName[random.randint(0, len(listName) - 1)]
        stringName = self.parseParens(stringName)
        stringName = self.parseBraces(stringName)
        stringName = stringName.strip()
        
        return stringName

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

class Subject(Reaction):
    columns = {}

    def __init__(self, inputFile = os.path.join(phraseDir, "Subjects.txt")):
        Reaction.__init__(self, inputFile)

class Greeting(Reaction):
    ignore = "`@\\"
    questionWords = "(?i)how|what|wh?a(ss|zz)up|('?sup)|ok(ay)?|al(l )?right"
    columns = {}

    def __init__(self, inputFile = os.path.join(phraseDir, "Greetings.txt")):
        Reaction.__init__(self, inputFile)

class Gossip(Reaction):
    ignore = "`@\\"
    columns = {}

    def __init__(self, inputFile = os.path.join(phraseDir, "Gossip.txt")):
        Reaction.__init__(self, inputFile)

class Idle(Reaction):
    ignore = "`@\\"
    columns = {}

    def __init__(self, inputFile = os.path.join(phraseDir, "Idling.txt")):
        Reaction.__init__(self, inputFile)

class Meta(Reaction):
    ignore = "`"
    columns = {}

    def __init__(self, inputFile = os.path.join(phraseDir, "Meta.txt")):
        Reaction.__init__(self, inputFile)
        

class DictInDict(Reaction):
    keyField = ""
    keyValues = {}
    
    def __init__(self, inputFile = "", key=""):
        self.keyField = key
        Reaction.__init__(self, inputFile)

    def readFile(self):
        try:
            if os.path.isfile(self.inputFile):
                fileHandler = open(self.inputFile, "r")
                lineNum = 0
                
                for line in fileHandler:
                    line = line.split(self.init["Splitters"]["field"])
                    headerField = ""
                    for field in line:
                        self.field = field.strip()
                        if self.field:
                            if 0 == lineNum:
                                self.header[self.index] = self.field.lower()
                                self.columns[self.field.lower()] = []
                            else:
                                if 0 == self.index:
                                    headerField = self.field.lower()
                                    self.keyValues[self.field.lower()] = {}
                                    for col in self.columns:
                                        if self.keyField <> col:
                                            self.keyValues[self.field.lower()][col] = ""
                                        else:
                                            self.keyValues[self.field.lower()][col] = self.field
                                else:
                                    try:
                                        self.keyValues[headerField][self.header[self.index]] = self.field
                                    except KeyError:
                                        pass
                        self.index += 1
                        
                    lineNum += 1
                    self.index = 0
            
                fileHandler.close()
            else:
                pass
        except IOError as ex:
            self.readFile()


class User(DictInDict):
    keyValues = {}
    keyField = "user"

    def __init__(self, inputFile = os.path.join(phraseDir, "Users.txt")):
        DictInDict.__init__(self, inputFile)

    def getGenders(self, user):
        user = self.getMainNick(user)
        try:
            if self.keyValues[user][self.init["Headers"]["user-gender"]]:
                genders = re.sub(r"\bm\b", self.init["Headers"]["subject-male"], self.keyValues[user][self.init["Headers"]["user-gender"]])
                genders = re.sub(r"\bf\b", self.init["Headers"]["subject-female"], genders)
                genders = re.sub(r"\bn\b", self.init["Headers"]["subject-neutral"], genders)
                genders = re.sub(r"\bpl\b", self.init["Headers"]["subject-plural"], genders)
                genders = genders.split(self.init["Splitters"]["gender"])
            else:
                genders = ["male", "fem", "neutral"]
        except KeyError:
            genders = ["male", "fem", "neutral"]
            
        return genders

    def getMainNick(self, nick):
        if nick:
            nick = nick.lower()
            if nick not in self.keyValues:
                for u in self.keyValues:
                    if re.search(r"\b{nick}\b".format(nick = nick), self.keyValues[u][self.init["Headers"]["user-alt"]].lower()):
                        nick = u
                        break
            
        return nick

    def randCallNick(self, user):
        initUser = str(user)
        user = str(user).lower()
        user = self.getMainNick(user)  
        try:
            nick = self.keyValues[user][self.init["Headers"]["user-nickcall"]].split(";")
            nick = random.choice(nick)
            if not nick:
                nick = initUser
        except KeyError:
            nick = initUser
        nick = self.parseParens(self.parseBraces(nick))
            
        return nick

class Song(Reaction):
    ignore = "`@\\"
    randTitle = True
    

    def __init__(self, inputFile = os.path.join(phraseDir, "Songs.txt")):
        self.listTitles = []
        self.listWorks = []
        self.byWork = {}
        self.byTitle = {}
        self.dumbedTitle = {}
        self.dumbedWork = {}
        self.columns = {}
        Reaction.__init__(self, inputFile)
        
    def addToList(self, theList, category, addWhat, dumbDict):
        if addWhat and category:
            try:
                if addWhat not in theList[category]:
                    theList[category].append(addWhat)
            except KeyError:
                dumbDict[self.dumbDown(category).lower()] = ""
                dumbDict[self.dumbDown(category).lower()] = category                   
                theList[category] = []
                theList[category].append(addWhat)

    def readFile(self):
        """ Sort songs by movie/work and sort quotes """
        """ by song and chronological order. """
        self.init = Settings.Settings().keywords
        
        try:
            if os.path.isfile(self.inputFile):
                with open(self.inputFile, "r") as fileHandler:
                    lineNum = 0
                    
                    for line in fileHandler:
                        lineNum += 1
                        line = line.split(self.init["Splitters"]["field"])
                        work = song = order = quote = artist = tag = ""
                        for f in line:
                            self.field = f.strip()
                            if 1 == lineNum:
                                self.header[self.field] = self.index
                                self.columns[self.field] = []
                            else:
                                if self.index == self.header[self.init["Headers"]["song-work"]]:
                                    work = f
                                elif self.index == self.header[self.init["Headers"]["song-song"]]:
                                    song = f
                                elif self.index == self.header[self.init["Headers"]["song-order"]]:
                                    order = int(f)
                                elif self.index == self.header[self.init["Headers"]["song-quote"]]:
                                    quote = f
                            self.index += 1
                        if lineNum > 1:
                            self.addToList(self.byWork, work, song, self.dumbedWork)
                            try:
                                self.byTitle[song][order] = quote
                            except KeyError:
                                ## Song wasn't encountered yet.
                                self.dumbedTitle[self.dumbDown(song).lower()] = ""
                                self.dumbedTitle[self.dumbDown(song).lower()] = song
                                self.byTitle[song] = {order: ""}
                                self.byTitle[song][order] = quote
                                
                        self.index = 0
            else:
                pass
        except IOError as ex:
            self.readFile()

    def getLists(self, arg):
        self.readFile()
        output = ""
        dumbArg = self.dumbDown(arg).lower()
        self.listTitles = [s for s in self.byTitle if s]
        self.listTitles.sort()
        self.listWorks = [w for w in self.byWork if w]
        self.listWorks.sort()
        if not dumbArg:
            output = "{s}".format(s=", ".join(["\"{s}\"".format(s=s) for s in self.listTitles]))
        elif "bycat" == dumbArg:
            output = "I have lyrics from these: {w}. (\"{sl} [category]\" for a list of songs from there)".format(w=", ".join(self.listWorks),
                                                                                                   sl=self.init["Commands"]["songlist"])
        elif dumbArg in self.dumbedTitle:
            output = "I have {n} lines from \"{s}\" waiting to be sung.".format(n=str(len(self.byTitle[self.dumbedTitle[dumbArg]])),
                                                                                s=self.dumbedTitle[dumbArg])
        elif dumbArg in self.dumbedWork:
            workSongs = [s for s in self.byWork[self.dumbedWork[dumbArg]]]
            workSongs.sort()
            workSongs = ", ".join("\"{s}\"".format(s=s) for s in workSongs)
            
            output = "From {w}, I have these songs: {s}".format(w=self.dumbedWork[dumbArg],
                                                                s=workSongs)
        else:
            output = "What's that? Maybe try \"{sl} bycat\", instead.".format(sl=self.init["Commands"]["songlist"])
            
        return output
    
    def getQuote(self, category):
        category = category.strip()
        quote = ""
        allQuotes = []
        song = self.getTitle(category)
        if not category:
            for s in self.byTitle:
                for o in self.byTitle[s]:
                    allQuotes.append(self.byTitle[s][o])
            quote = random.choice(allQuotes)
            song = self.getTitle(quote)
            self.randTitle = True
        elif song:
            quote = self.byTitle[song][random.randint(1, len(self.byTitle[song]))]
        if quote:
            quote = self.parseParens(self.parseBraces(quote)).strip()
            if self.randTitle:
                quote = quote +" (\"{s}\")".format(s=song)
        
        return quote

    def getTitle(self, line): 
        self.readFile()
        song = ""
        dumbLine = self.dumbDown(line).lower()
        if dumbLine:
            if dumbLine in self.dumbedTitle:
                song = self.dumbedTitle[dumbLine]
                self.randTitle = False
            elif dumbLine in self.dumbedWork:
                song = random.choice(self.byWork[self.dumbedWork[dumbLine]])
                self.randTitle = True
            else:
                for s in self.byTitle:
                    for o in self.byTitle[s]:
                        if self.dumbRegex(line).search(self.byTitle[s][o]):
                            song = s
                            self.currentQ = self.byTitle[s][o]
                            self.randTitle = True
        return song

class SingAlong(Song):

    def __init__(self, inputFile = os.path.join(phraseDir, "SingAlong.txt")):
        Song.__init__(self, inputFile)
        self.currentOrder = None
        self.currentQ = ""
        self.currentTitle = ""
        self.currentOrder = 0
        self.autoCompleted = False
        self.lenTitle = 0

    def autoNext(self):
        quote = ""
        if 0 == self.currentOrder:
            quote = self.byTitle[self.currentTitle][1]
            self.currentOrder += 1
        else:
            order = self.currentOrder
##            if not self.autoCompleted:
##                order += 1
            try:
                quote = self.byTitle[self.currentTitle][order]
            except KeyError:
                quote = self.byTitle[self.currentTitle][order - 1]

        self.currentOrder += 1
        self.currentQ = quote
        self.autoCompleted = False
        
        return quote

    def nextLine(self, line):
        self.autoCompleted = False
        line = line.strip()
        quote = ""
        if not self.currentTitle:
            self.currentTitle = self.getTitle(line)
            self.lenTitle = len(self.byTitle[self.currentTitle])
            return "Started \"{song}\". (\"{stop}\" to quit the song.)".format(song=self.currentTitle,
                                                                               stop=self.init["Commands"]["stopsong"])
        if not re.search(r"\w", line):
            return None
        titleQuotes = self.byTitle[self.currentTitle]
        if not self.currentOrder:
            self.currentOrder = 1

        self.lenTitle = len(titleQuotes)

        allQuotes = []
        tempOrder = self.currentOrder
        line = self.dumbRegex(line)
        
        for o in titleQuotes:
            if tempOrder == o:
                if line.search(self.dumbDown(titleQuotes[o]).replace("_", " ")):
                    self.currentQ = titleQuotes[o]
                    self.currentOrder = tempOrder

                    ## For line auto-completion, try to split the quote with
                    ## the first instance of the line to to check for leftovers.
                    quote = line.split(self.currentQ, 1)
                    quote = quote[len(quote) - 1]

                    try:
                        if quote.strip(" ,.?-:;!"):
                            self.autoCompleted = True
                        else:
                            quote = titleQuotes[self.currentOrder + 1]
                            self.currentQ = titleQuotes[self.currentOrder + 1]
                            self.currentOrder += 1
                    except KeyError:
                        self.currentQ = titleQuotes[self.currentOrder]
                        return None
                    
                    self.currentOrder += 1
                    break
                allQuotes.append(titleQuotes[o])
                tempOrder += 1

        allQuotes = "\n".join(allQuotes)
        if not quote:
            ## Maybe they said more than one line in the song.
            if line.search(self.dumbDown(allQuotes).replace("_", " ")):
                allQuotes = line.split(allQuotes, 1)
                allQuotes = allQuotes[len(allQuotes) - 1].split("\n")
                quote = allQuotes[0]

                if quote.strip(" ,.?-:;!"):
                    if len(allQuotes) > 1:
                        for o in titleQuotes:
                            if titleQuotes[o] == allQuotes[1]:
                                self.currentQ = titleQuotes[o - 1]
                                self.autoCompleted = True
                                self.currentOrder = o
                                break
                    else:
                        self.currentQ = titleQuotes[len(titleQuotes)]
                        self.currentOrder = len(titleQuotes)
                else:
                    quote = allQuotes[1]
                    self.autoCompleted = False
                    self.currentQ = quote
                    for o in titleQuotes:
                        if titleQuotes[o] == quote:
                            self.currentOrder = o
                            break

        ## If the line wasn't found, it probably wasn't part of the song.         
        return quote.lstrip(" ,.?-:;!'")

class Recital(SingAlong):
    def __init__(self, inputFile = os.path.join(phraseDir, "Recite.txt")):
        SingAlong.__init__(self, inputFile)
        self.delay = 2.5

    def autoNext(self):
        quote = ""
        self.lenTitle = len(self.byTitle[self.currentTitle])
        if 0 == self.currentOrder:
            quote = "\"{t}\" (\"{stop}\" if you had enough.)".format(t=self.currentTitle, stop=self.init["Commands"]["stoppoem"])
        else:
            order = self.currentOrder
            try:
                quote = self.byTitle[self.currentTitle][order][0]
                self.delay = self.byTitle[self.currentTitle][order][1]
            except KeyError:
                quote = self.byTitle[self.currentTitle][order - 1][0]
                self.delay = self.byTitle[self.currentTitle][order - 1][1]

        self.currentOrder += 1
        self.currentQ = quote
        self.autoCompleted = False
        print(self.lenTitle, self.currentOrder)
        
        return quote

    def getLists(self, arg):
        self.readFile()
        output = ""
        dumbArg = self.dumbDown(arg).lower()
        for w in self.byWork:
            for t in self.byWork[w]:
                if t not in self.listTitles:
                    self.listTitles.append("\"{t}\" ({w})".format(t=t, w=w))
                                       
        self.listWorks = [w for w in self.byWork if w]
        self.listWorks.sort()
        
        if not dumbArg:
            output = "{s}".format(s=", ".join(["{s}".format(s=s) for s in self.listTitles]))
        elif "bycat" == dumbArg:
            output = "I have lines from: {w}. (\"{pl} [who]\" for a list of stuff I can recite.)".format(w=", ".join(self.listWorks),
                                                                                                   pl=self.init["Commands"]["poemlist"])
        elif dumbArg in self.dumbedTitle:
            output = "I have {n} lines from \"{s}\" waiting to be recited.".format(n=str(len(self.byTitle[self.dumbedTitle[dumbArg]])),
                                                                                s=self.dumbedTitle[dumbArg])
        elif dumbArg in self.dumbedWork:
            workPoems = [s for s in self.byWork[self.dumbedWork[dumbArg]]]
            workPoems.sort()
            workPoems = ", ".join("\"{s}\"".format(s=s) for s in workPoems)
            output = "From {w}, I have these: {s}".format(w=self.dumbedWork[dumbArg],
                                                          s=workPoems)
        else:
            output = "What's that? Maybe try \"{pl} bycat\", instead.".format(pl=self.init["Commands"]["poemlist"])
            
        return output

    def getTitle(self, line): 
        self.readFile()
        title = ""
        dumbLine = self.dumbDown(line).lower()
        if dumbLine:
            if dumbLine in self.dumbedTitle:
                title = self.dumbedTitle[dumbLine]
                self.randTitle = False
            elif dumbLine in self.dumbedWork:
                song = random.choice(self.byWork[self.dumbedWork[dumbLine]])
                self.randTitle = True
            else:
                for s in self.byTitle:
                    for o in self.byTitle[s]:
                        if self.dumbRegex(line).search(self.byTitle[s][o][0]):
                            title = s
                            self.currentQ = self.byTitle[s][o][0]
                            self.randTitle = True
        return title


    def readFile(self):
        """ Sort songs by movie/work and sort quotes """
        """ by song and chronological order. """
        self.init = Settings.Settings().keywords
        
        try:
            if os.path.isfile(self.inputFile):
                with open(self.inputFile, "r") as fileHandler:
                    lineNum = 0
                    
                    for line in fileHandler:
                        lineNum += 1
                        line = line.split(self.init["Splitters"]["field"])
                        work = song = order = quote = artist = tag = ""
                        for f in line:
                            self.field = f.strip()
                            if 1 == lineNum:
                                self.header[self.field] = self.index
                                self.columns[self.field] = []
                            else:
                                if self.index == self.header[self.init["Headers"]["poem-work"]]:
                                    work = f
                                elif self.index == self.header[self.init["Headers"]["poem-title"]]:
                                    song = f
                                elif self.index == self.header[self.init["Headers"]["poem-order"]]:
                                    order = int(f)
                                elif self.index == self.header[self.init["Headers"]["poem-quote"]]:
                                    quote = f
                                elif self.index == self.header[self.init["Headers"]["poem-delay"]]:
                                    delay = float(f)
                            self.index += 1
                        if lineNum > 1:
                            self.addToList(self.byWork, work, song, self.dumbedWork)
                            try:
                                self.byTitle[song][order] = (quote, delay)
                            except KeyError:
                                ## Song wasn't encountered yet.
                                self.dumbedTitle[self.dumbDown(song).lower()] = ""
                                self.dumbedTitle[self.dumbDown(song).lower()] = song
                                self.byTitle[song] = {order: ""}
                                self.byTitle[song][order] = (quote, delay)
                                
                        self.index = 0
            else:
                self.logger.error("{f} does not exist.".format(f = self.inputFile))
        except IOError as ex:
            self.closeLogHandlers()
            self.makeLogger()
            self.readFile()

class HelpMe(DictInDict):
    keyValues = {}
    keyHeader = "cmd"

    def __init__(self, inputFile = os.path.join(phraseDir, "Help.txt")):
        self.dumbKeyValues = {}
        DictInDict.__init__(self, inputFile)

    def getHelp(self, arg):
        for k in self.keyValues:
            self.dumbKeyValues[re.sub(r"\W", "", k).lower()] = self.keyValues[k]
            
        output = ""
        listCmds = ["{c}".format(c=cmd) for cmd in self.keyValues]
        listCmds.sort()
        listCmds = ", ".join(listCmds)
        arg = re.sub(r"\W", "", arg)
        if not arg:
            output = "Special things I respond to: {c}. (\"{h} [topic]\" for a description)".format(c=listCmds,
                                                                                                                              h=self.init["Commands"]["help"])
        else:
            if arg in self.dumbKeyValues:
                output = self.dumbKeyValues[arg]["description"]
            else:
                output = self.dumbKeyValues["halp"]["description"]
            
        return output

class Link(DictInDict):
    keyValues = {}
    keyHeader = "trigger"

    def __init__(self, inputFile = os.path.join(phraseDir, "Links.txt")):
        self.dumbKeyValues = {}
        DictInDict.__init__(self, inputFile)

        for k in self.keyValues:
            self.dumbKeyValues[k.lower()] = self.keyValues[k]

    def getList(self):
        linkList = ["{k} - {l}".format(k=k, l=self.keyValues[k]["link"]) for k in self.keyValues]
        linkList.sort()
        
        return linkList

    def getTrigger(self, arg):
        if not arg:
            return self.getList()
        else:
            index = 0
            for t in self.keyValues.values():
                if arg in self.keyValues.values()[index]["link"]:
                    for trigger in self.keyValues:
                        if self.keyValues[trigger]["link"] == arg:
                            return trigger
                index += 1

            return "Doesn't seem like the link was added yet. \"{l}\" for a list of {n} links.".format(l=self.init["Commands"]["link"],
                                                                                                       n=len(self.keyValues))

class Quote(DictInDict):
    keyValues = {}
    keyHeader = "id"

    def __init__(self, inputFile=os.path.join(phraseDir, "Quotes.txt")):
        DictInDict.__init__(self, inputFile)

    def getCategories(self, category):
        category = category.strip().lower()
        categories = []
        if not category:
            for x in set([x["category"] for x in self.keyValues.values()]):
                categories.append("{} ({})".format(x, len([m for m in self.keyValues if x == self.keyValues[m]["category"]])))

            categories = "I have quotes from these categories: {}".format(", ".join(categories))
        else:
            categories = list(set([self.keyValues[x]["by"] for x in self.keyValues if self.keyValues[x]["category"].lower().strip() == category]))
            categories.sort()
            if not categories:
                categories = "\"{}\" to have me list the categories of quotes I have. \"{}\" to have me pick a random quote.".format(self.init["Commands"]["quotecat"], self.init["Commands"]["quote"])
            else:
                categories = "In {}, I have quotes from {}".format(category, ", ".join(categories))

        return categories

    def getQuote(self, category):
        idNum, quote, cat, by, date = "", "", "", "", ""
        if not category:
            idNum = random.choice(self.keyValues.keys())
            quote = self.keyValues[idNum]["quote"]
            cat = self.keyValues[idNum]["category"]
            by = self.keyValues[idNum]["by"]
            date = self.keyValues[idNum]["date"]
        else:
            matches = []
            catFilter = re.search(r"(.*?)(?:index=|by=|words=|$)", category, re.I)
            if catFilter:
                catFilter = self.dumbDown(catFilter.group(1)).lower()
            if not catFilter:
                catFilter = ".*"
            wordFilter = re.search(r"words=(.+?)(?:index=|by=|$)", category, re.I)
            if wordFilter:
                wordFilter = self.dumbDown(wordFilter.group(1))
            else:
                wordFilter = ".*"
            byFilter = re.search(r"by=(.+?)(?:index=|words=|$)", category, re.I)
            if byFilter:
                byFilter = self.dumbDown(byFilter.group(1)).lower()
            else:
                byFilter = ".*"
            orderFilter = re.search(r"index=(\d+\s*)(?:words=|by=|$)", category, re.I)
            if orderFilter:
                orderFilter = int(orderFilter.group(1)) - 1

            matches = [int(x) for x in self.keyValues if re.match("{}$".format(catFilter), self.keyValues[x]["category"].strip(), re.I) and re.search(wordFilter, self.keyValues[x]["quote"], re.I)
                       and re.search(byFilter, self.keyValues[x]["by"], re.I)]
            matches.sort()
            
            try:
                if 0 > orderFilter or "" == orderFilter:
                    orderFilter = random.randint(0, len(matches) - 1)
                    
                index = str(matches[orderFilter])
                quote = self.keyValues[index]["quote"]
                by = self.keyValues[index]["by"]
                cat = self.keyValues[index]["category"]
                date = self.keyValues[index]["date"]
            except ValueError:
                return "No matching quotes found."
            except IndexError:
                return "Index not found. (Only {} matches found)".format(len(matches))

        if date:
            quote = "\"{}\" - {} ({}, {})".format(quote, by, cat, date)
        else:
            quote = "\"{}\" - {} ({})".format(quote, by, cat)

        return quote
