# -*- coding: utf-8 -*-
try:
    import ConfigParser as configparser  # Python 2
except ImportError:
    import configparser  # Python 3
import logging
import logging.config
import os.path
import random
import re
import sqlite3

DEFAULT_KEY = "id"
DIR_DATABASE = os.path.join(os.path.dirname("__file__"), "database")
DIR_LOG = os.path.join(os.path.dirname("__file__"), "log")
FILE_DATABASE = "meatbot.sqlite3"
FILE_DUMBREGEX = "dumb_regex.ini"
FILE_SETTINGS = "settings.ini"

config = configparser.SafeConfigParser()
config.read(os.path.join(DIR_DATABASE, FILE_SETTINGS))

logging.config.fileConfig("logging.ini")
logger = logging.getLogger("lineparser")


## === Functions === ##
def clean(line):
    return "".join(char for char in line if char.isalnum())

def dumb_down(line, preserveCase=False):
    """
    Simple way to "dumb" a string down to make matching less strict. Replaces non-word characters with underscores.

    Args:
        line(str): Line to dumb down.
        preserveCase(bool, optional): If True, case is preserved. Else, it is turned to lowercase.
        
    Returns:
        line(str, re.RegexObject): Resulting pattern.

    Examples:
        >>> dumb_down("Give me underscores, please.")
        give_me_underscores_please
    """
    line = line.rstrip(" ,.!?-")
    line = line.strip()
    line = re.sub(r"\W", "", line.replace(" ", "_"))
    while "__" in line:
        line = line.replace("__", "_").strip("_ ")

    if not preserveCase:
        line = line.lower()
        
    return line

def dumb_regex(line, willCompile=True):
    """
    Makes matching a line to be much more permissive.
    The result is meant to be used for regex pattern matching.

    Args:
        line(str): Line to dumb down.
        willCompile(bool, optional): Whether to return line as compiled regex object (True) or not.

    Returns:
        line(str, re.RegexObject): Resulting pattern.

    Examples:
        >>> dumb_regex("Hello.", False)
        (?i)(h-?)+(e-?)+(l-?)+(o-?)+
    """
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
        line = re.sub(r"(?i)({}(?!\*)(?!-\?)-?)+".format(char), "({}-?)+".format(char), line)
    line = re.sub(r"(?<=[^\\])(w-?)+", "(w-?)+", line)
    
    ## Case won't matter.
    line = "(?i){l}".format(l=line)

    if willCompile:
        line = re.compile(line)

    return line

def get_setting(section, key):
    try:
        return config.get(section, key).decode("string-escape")  # Python 2
    except AttributeError:
        return config.get(section, key).decode("unicode-escape")  # Python 3

def parse_choices(stringParse):
    """
    Chooses a random option in a given set.

    Args:
        stringParse(str): String to parse. Options are enclosed in angle brackets, separated by a pipeline.

    Yields:
        newString(str): An option from the leftmost set of options is chosen for the string and updates accordingly.

    Raises:
        StopIteration: stringParse's options are all chosen.

    Examples:
        >>> next(parse_choices("<Chocolates|Sandwiches> are the best!"))
        "Chocolates are the best!"

        >>> result = parse_choices("I would like some <cupcakes|ice cream>, <please|thanks>.")
        >>> for _ in result: print(next(result))
        I would like some <cupcakes|ice cream>, thanks.
        I would like some cupcakes, thanks.
    """

    OPEN_CHAR = get_setting("Variables", "open_choose")
    CLOSE_CHAR = get_setting("Variables", "close_choose")
    ESCAPE_CHAR = get_setting("Variables", "escape")
    SPLITTER = get_setting("Variables", "parse_choose")
    done = False

    while not done:
        if OPEN_CHAR not in stringParse or CLOSE_CHAR not in stringParse:
            done = True
            
        level = 0
        escapeNum = 0
        openIndex = 0
        closeIndex = 0
        optionNum = 0
        options = []
        
        for index, char in enumerate(stringParse):
            if OPEN_CHAR == char and not escapeNum % 2:
                level += 1
                if 1 == level:
                    openIndex = index
                    options.append([])
                elif level:
                    options[optionNum].append(char)
            elif CLOSE_CHAR == char and not escapeNum % 2:
                level -= 1
                if 0 == level:
                    ## First and outermost level gathered.
                    closeIndex = index
                    break
                elif level:
                    options[optionNum].append(char)
            elif SPLITTER == char and not escapeNum % 2:
                if 1 == level:
                    optionNum += 1
                    options.append([])
                elif level:
                    options[optionNum].append(char)
            elif ESCAPE_CHAR == char:
                escapeNum += 1
                if level:
                    options[optionNum].append(char)
            else:
                escapeNum = 0
                if level:
                    options[optionNum].append(char)
                
        tmpBlock = stringParse[openIndex:closeIndex + 1]
        
        if 1 < len(tmpBlock):
            stringParse = stringParse.replace(tmpBlock, "".join(random.choice(options)))
        else:
            done = True
            
        yield stringParse
    
def parse_optional(stringParse):
    """
    Chooses whether to omit a substring or not.

    Args:
        stringParse(str): String to parse. Substring to be reviewed is enclosed in braces.

    Yields:
        stringParse(str): The string with or without the leftmost substring, stripped of the braces.

    Raises:
        StopIteration: stringParse's braces are fully parsed.

    Examples:
        >>> next(parse_optional("You're mean{ingful}."))
        "You're meaningful."

        >>> result = parse_optional("You're pretty{{ darn} awful}.")
        >>> for _ in result: print(next(result))
        You're pretty{ darn} awful.
        You're pretty awful.
    """
    
    OPEN_CHAR = get_setting("Variables", "open_omit")
    CLOSE_CHAR = get_setting("Variables", "close_omit")
    ESCAPE_CHAR = get_setting("Variables", "escape")
    done = False

    while not done:
        if OPEN_CHAR not in stringParse or CLOSE_CHAR not in stringParse:
            done = True
            
        level = 0
        escapeNum = 0
        openIndex = 0
        closeIndex = 0
        
        for index, char in enumerate(stringParse):
            if OPEN_CHAR == char and not escapeNum % 2:
                level += 1
                if 1 == level:
                    openIndex = index
            elif CLOSE_CHAR == char and not escapeNum % 2:
                level -= 1
                if 0 == level:
                    ## First and outermost level gathered.
                    closeIndex = index
                    break
            elif ESCAPE_CHAR == char:
                escapeNum += 1
            else:
                escapeNum = 0
                
        tmpBlock = stringParse[openIndex:closeIndex + 1]
        
        if 1 < len(tmpBlock):
            if random.getrandbits(1):
                stringParse = "".join([stringParse[:openIndex], stringParse[closeIndex + 1:]])
            else:
                stringParse = "".join([stringParse[:openIndex], stringParse[openIndex + 1:closeIndex], stringParse[closeIndex + 1:]])
        else:
            done = True
            
        yield stringParse

def parse_all(stringParse):
    """
    Combines parse_choices() with parse_optional() and takes care of escape characters.

    Args:
        stringParse(str): String to parse.

    Returns:
        stringParse(str): Updated string.

    Examples:
        >>> parse_all("I'm {b}eating you{r <cake|homework>}.")
        I'm eating your homework.
    """

    if (get_setting("Variables", "open_omit") in stringParse
    and get_setting("Variables", "close_omit") in stringParse):
        for result in parse_optional(stringParse):
            stringParse = result

    if (get_setting("Variables", "open_choose") in stringParse
    and get_setting("Variables", "open_choose") in stringParse):
        for result in parse_choices(stringParse):
            stringParse = result

    ## Parse escape characters.
    stringParse = stringParse.replace("{e}{e}".format(e=get_setting("Variables", "escape")), get_setting("Variables", "sentinel"))
    stringParse = stringParse.replace(get_setting("Variables", "escape"), "")
    stringParse = stringParse.replace(get_setting("Variables", "sentinel"), get_setting("Variables", "escape"))

    return stringParse

def set_config(filepath=os.path.join(DIR_DATABASE, FILE_SETTINGS)):
    global config
    config.read(filepath)

def substitute(line, variables=None):
    """
    Substitutes given values in a single line.

    Args:
        line(str): Line to substitute values into.
        variables(dict): Values of placeholders you want to define in the following format:
            {"placeholder": "real value",}

    Returns:
        line(str): The line with every placeholder replaced.

    Examples:
        >>> substitute("%title% Hans of the Southern Isles.", {"%title%": "Princess"})
        Princess Hans of the Southern Isles.
    """
    if isinstance(variables, dict):
        for var in variables:
            line = line.replace(var, variables[var])

    line = "".join([line.replace(get_setting("Variables", "action"), "\001ACTION"), "\001"])

    return line


## === Classes === ##
class LineParser(object):
    """
    For reading and parsing lines in a SQLite database.
    """
    def __init__(self, dbFile):
        self.db = dbFile

    def clean(self, table):
        return "".join(c for c in table if c.isalnum())

    def get_column(self, table, header, maximum=None):
        """
        Gets fields under a column header.

        Args:
            header(str): Name of column's header.
            table(str): Name of table.
            maximum(int, optional): Maximum amount of fields to fetch.

        Returns:
            fields(list): List of fields under header.
        """
        fields = []
        table = self.clean(table)
        connection = sqlite3.connect(os.path.join(DIR_DATABASE, FILE_DATABASE))
        c = connection.cursor()
        if maximum:
            c.execute("SELECT {} FROM {} LIMIT ?".format(header, table), [maximum])
        else:
            c.execute("SELECT {} FROM {}".format(header, table))
        fields = c.fetchall()
        c.close()
        
        return fields

    def get_field(self, fieldId, header, table):
        """
        Gets the field under the specified header, identified by its primary key value.

        Args:
            primaryKeyValue(int, str): Unique ID of line the field is in.
            header(str): Header of the field to fetch.

        Returns:
            The desired field, or None if the lookup failed.

        Examples:
            >>> get_field(123, "firstname")
            Adgar
        """
        header = self.clean(header)
        table = self.clean(table)
        field = ""
        
        connection = sqlite3.connect(os.path.join(DIR_DATABASE, FILE_DATABASE))
        c = connection.cursor()
        c.execute("SELECT {} FROM {} WHERE id=?".format(header, table), [fieldId])

        try:
            field = c.fetchone()[0]
        except TypeError:
            logger.error("ID \"{}\" was not in table \"{}\"".format(fieldId, table))
        
        c.close()
        
        return field

    def get_keys(self, category=None, dumb="", splitter=","):
        """
        Gets the keys that fit within the specified categories. Gets all keys if category is None.

        Args:
            category(dict, optional): Categories you want to filter the line by.
                {"header of categories 1": "category1,category2", "header of category 2": "category3"}
                Multiple categories under a single header are separated with a comma.
            dumb(str, optional): Whether to perform a "dumb" search or not.
                "simple" uses dumb_down function.
                "regex" uses dumb_regex function (with a compiled regex object).
                Any other value uses a strict search.
            splitter(str, optional): What separates multiple categories (default is a comma).

        Returns:
            keys(list): List of keys that match the categories.

        Examples:
            >>> get_keys({"type": "greeting"})
            [1, 2, 3, 5, 9, 15]
        """
        
        keys = list(self._lines.keys())
        if category is not None:
            for header in category:
                if header in self._categories:
                    cats = category[header].split(splitter)

                    ## Validating given categories.
                    invalidCats = set()
                    for c in cats:
                        if c not in self._categories[header]:  # c is not a known category in the column under header.
                            invalidCats.add(c)

                    cats = [c for c in cats if c not in invalidCats]
                    
                    ## Filtering the keys according to category.
                    ## Multiple categories under the same header are treated as "if key is under category1 or category2".
                    ## But the key must belong to at least one of a category across multiple headers.
                    ##     e.g. {"type": "greeting,bye", "servers": "TheBest"} looks for a line that is type "greeting" or "bye", and the servers "TheBest".
                    tempKeys = []
                    for c in cats:
                        for key in keys:
                            if key in self._categories[header][c]:
                                tempKeys.append(key)
                    keys = list(set(tempKeys))

        return keys

    def random_line(self, lineHeader, category=None):
        """
        Chooses a random line from the database under the header lineHeader.

        Args:
            lineHeader(str): The header of the column where you want a random line from.
            category(dict): Categories you want to filter the line by, formatted like so:
                {"header of categories 1": "category1,category2", "header of category 2": "category3"}
                Multiple categories under a single header are separated with a comma.

        Returns:
            line(str): A random line from the database.

        Raises:
            IndexError: If the filters in category do not match any keys in the database, or the class's dictionary of lines is empty
                (say, if read_file() was not called, or the file read was empty.)
            KeyError: If lineHeader is not an existing header in the file.

        Examples:
            >>> random_line("line", {"type": "greeting"})
            Hello.
        """
        
        line = ""
        choices = self.get_keys(category)

        try:
            line = self._lines[random.choice(choices)][lineHeader]
        except IndexError:
            print('"{}" did not match any key.'.format(category))
        except KeyError:
            print('"{}" is not an existing header in the file.'.format(lineHeader))

        return line


class Singalong(LineParser):
    def __init__(self, inputFile, songFile, primaryKey=DEFAULT_KEY, songKey=DEFAULT_KEY):
        LineParser.__init__(self, inputFile, primaryKey)
        self.lineNum = 0
        self.song = None
        self.songFile = LineParser(songFile, songKey)

    def next_line(self, line, auto=False):
        """
        Gets the next line of the current song.
        """
        if auto:
            try:
                line = [k for k in self.get_keys({"title": self.song.title, "autonext": "yes"}) if self.lineNum < int(self.get_field(k, "order"))][0]
            except IndexError:
                return None

            self.lineNum = self.get_field(line, "order")
            line = self.get_field(line, "line")
        else:
            dumbLine = self.dumb_regex(line, True)
            
            lyrics = [self.get_field(k, "line") for k in self.get_keys({"title": self.song.title}) if self.lineNum < int(self.get_field(k, "order"))]
            lyrics = dumbLine.split("\n".join(lyrics), 1)
            line = lyrics[len(lyrics) - 1].split("\n")[0]
            ## Update song progress.
            
        return line

    def set_song(self, key):
        title = self.songFile.get_field(key, "title")
        category = self.songFile.get_field(key, "category")
        version = self.songFile.get_field(key, "version")
        
        self.song = Song(title, key, category, version)
        self.song.length = len([self.get_keys({"title": title})])


class Song(object):
    """ Conveniently stores a song's properties. """
    def __init__(self, title, songID, category="", version=""):
        self.title = title
        self.songID = songID
        self.category = category
        self.version = version
        self.singers = []
        self.length = 0
        

def test_parser():
    r = parse_all(r"<HAPPY BIRTHDAY <A|U>NNA|DRY \{\{\}\} \\{B{AN}}ANA HIPPY HAT>{<!|?>}")
    print(r)

def test_sql():
    s = LineParser(os.path.join(DIR_DATABASE, FILE_DATABASE))
    print(s.get_field(3, "line", "phrases"))

def test_insert(inputFile):
    columns = {0: 10,
               1: 10,
               2: 11,
               3: 8,
               4: 13,}
    try:
        connection = sqlite3.connect(os.path.join(DIR_DATABASE, FILE_DATABASE))
        c = connection.cursor()
        
        if os.path.isfile(inputFile):
            with open(inputFile, "r") as fileHandler:
                lineNum = 0
                
                for line in fileHandler:
                    index = 0
                    trigger = ""
                    reaction = ""
                    lineNum += 1
                    line = line.split("\t")
                    for field in line:
                        if not 1 == lineNum and field.strip():
                            if 0 == index:
                                trigger = "\\{}".format(field.strip())
                            else:
                                reaction = field.strip()
                            
                        index += 1
                    c.execute("INSERT INTO triggers(trigger, reaction, case_sensitive, alert, reaction_chance) VALUES(?, ?, 0, 0, 100)", (trigger, reaction))
        else:
            print("{f} does not exist.".format(f=inputFile))
        
        connection.commit()
    except IOError as ex:
        print("IO Error encountered: {args}".format(args = str(ex.args)))
    finally:
        c.close()
    
if "__main__" == __name__:
    test_sql()
