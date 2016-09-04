# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
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
FILE_DATABASE = os.path.join(DIR_DATABASE, "meatbot.sqlite3")
FILE_DUMBREGEX = os.path.join(DIR_DATABASE, "dumb_regex.ini")
FILE_SETTINGS = os.path.join(DIR_DATABASE, "settings.ini")

config = configparser.SafeConfigParser()
config.read(FILE_SETTINGS)

logging.config.fileConfig("logging.ini")
logger = logging.getLogger("lineparser")

try:
    unicode  # Python 2
except NameError:
    unicode = str  # Python 3


## === Functions === ##
def clean(line):
    """
    Strip a string of non-alphanumerics (except underscores). Can use to clean strings before using them in a database query.

    Args:
        line(unicode): String to clean.

    Returns:
        line(unicode): A string safe to use in a database query.

    Examples:
        >>> clean("Robert'); DROP TABLE Students;")
        Robert
    """
    return "".join(char for char in line if (char.isalnum() or "_" == char))

def dumb_simple(line, preserveCase=False):
    """
    Simple way to "dumb" a string down to make matching less strict. Replaces non-word characters with underscores.

    Args:
        line(unicode): Line to dumb down.
        preserveCase(bool, optional): If True, case is preserved. Else, it is turned to lowercase.
        
    Returns:
        line(unicode, re.RegexObject): Resulting pattern.

    Examples:
        >>> dumb_simple("Give me underscores, please.")
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
        line(unicode): Line to dumb down.
        willCompile(bool, optional): Whether to return line as compiled regex object (True) or not.

    Returns:
        line(unicode, re.RegexObject): Resulting pattern.

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
        return bytes(config.get(section, key)).decode("string-escape")  # Python 2
    except (AttributeError, TypeError):
        return bytes(config.get(section, key), "utf-8").decode("unicode-escape")  # Python 3

def match_dumbsimple(expression, line):
    expression = dumb_simple(expression)

    if line:
        return expression == dumb_simple(line)

def match_dumbregex(expression, line):
    expression = dumb_regex(expression)

    if line:
        return expression.search(line) is not None

def parse_choices(stringParse):
    """
    Chooses a random option in a given set.

    Args:
        stringParse(unicode): String to parse. Options are enclosed in angle brackets, separated by a pipeline.

    Yields:
        newString(unicode): An option from the leftmost set of options is chosen for the string and updates accordingly.

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
        stringParse(unicode): String to parse. Substring to be reviewed is enclosed in braces.

    Yields:
        stringParse(unicode): The string with or without the leftmost substring, stripped of the braces.

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
        stringParse(unicode): String to parse.

    Returns:
        stringParse(unicode): Updated string.

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

def regexp(expression, line):
    reg = re.compile(expression)

    if line:
        return reg.search(line) is not None
    
def set_config(filepath=FILE_SETTINGS):
    global config
    config.read(filepath)

def substitute(line, variables=None):
    """
    Substitutes given values in a single line.

    Args:
        line(unicode): Line to substitute values into.
        variables(dict): Values of placeholders you want to define in the following format:
            {"placeholder": "real value",}

    Returns:
        line(unicode): The line with every placeholder replaced.

    Examples:
        >>> substitute("%title% Hans of the Southern Isles.", {"%title%": "Princess"})
        Princess Hans of the Southern Isles.
    """
    if isinstance(variables, dict):
        for var in variables:
            logger.debug("Substitution variable: {} -> {}".format(var, variables[var]))
            line = line.replace(var, variables[var])

    if get_setting("Variables", "action") in line:
        line = "".join([line.replace(get_setting("Variables", "action"), "\001ACTION"), "\001"])

    return line


## === Classes === ##
class Database(object):
    """
    For reading and parsing lines in a SQLite database.

    Args:
        dbFile(unicode): The filepath of the database.
    """
    SEARCH_DEFAULT = "="
    SEARCH_SIMPLE = "simple"
    SEARCH_DUMBREGEX = "dumbregex"
    SEARCH_REGEX = "regex"

    SEARCH_FUNCTIONS = {SEARCH_SIMPLE: match_dumbsimple,
                       SEARCH_DUMBREGEX: match_dumbregex,
                       SEARCH_REGEX: regexp,}
    
    def __init__(self, dbFile):
        self.db = dbFile

    def get_column(self, header, table, maximum=None):
        """
        Gets fields under a column header.

        Args:
            header(unicode): Name of column's header.
            table(unicode): Name of table.
            maximum(int, optional): Maximum amount of fields to fetch.

        Returns:
            fields(list): List of fields under header.
        """
        fields = []
        table = clean(table)
        connection = sqlite3.connect(self.db)
        connection.row_factory = lambda cursor, row: row[0]
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
            fieldId(int, str): Unique ID of line the field is in.
            header(unicode): Header of the field to fetch.
            table(unicode): Name of table to look into.

        Returns:
            The desired field, or None if the lookup failed.

        Raises:
            TypeError: If fieldId doesn't exist in the table.
        
        Examples:
            >>> get_field(123, "firstname", "kings")
            Adgar
        """
        header = clean(header)
        table = clean(table)
        field = None
        
        connection = sqlite3.connect(self.db)
        c = connection.cursor()
        c.execute("SELECT {} FROM {} WHERE id=?".format(header, table), [fieldId])

        try:
            field = c.fetchone()[0]
        except TypeError:
            logger.exception("ID \"{}\" was not in table \"{}\"".format(fieldId, table))
        
        c.close()
        
        return field

    def get_ids(self, table, category=None, searchMode="", splitter=","):
        """
        Gets the IDs that fit within the specified categories. Gets all IDs if category is None.

        Args:
            table(unicode): Name of table to look into.
            category(dict, optional): Categories you want to filter the line by.
                {"header of categories 1": "category1,category2", "header of category 2": "category3"}
                Multiple categories under a single header are separated with a comma.
                If categories are provided, the line must match at least one category in each header.
            searchMode(unicode, optional): Determines the method of searching for matches.
                Database.SEARCH_SIMPLE ("simple) uses match_dumbsimple function.
                Database.SEARCH_REGEX ("regex") uses regexp function.
                Database.SEARCH_DUMBREGEX ("dumbregex") uses match_dumbregex function.
                Any other value uses a strict search.
            splitter(unicode, optional): What separates multiple categories (default is a comma).

        Returns:
            ids(list): List of IDs that match the categories.

        Raises:
            OperationalError: If table or header doesn't exist.
            TypeError: If category is neither None nor a dictionary.

        Examples:
            >>> get_ids({"type": "greeting"})
            [1, 2, 3, 5, 9, 15]  # Any row that has the type "greeting".

            >>> get_ids({"type": "nickname,quip", "by": "Varric"})
            [23, 24, 25, 34, 37, 41, 42, 43]  # Any row by "Varric" that has the type "nickname" or "quip".
        """
        ids = []
        table = clean(table)
        clause = ""
        
        connection = sqlite3.connect(self.db)
        connection.row_factory = lambda cursor, row: row[0]  # Outputs first element of tuple for fetchall()

        if searchMode in self.SEARCH_FUNCTIONS:  # Use appropriate custom function to search for matches.
            connection.create_function("REGEXP", 2, self.SEARCH_FUNCTIONS[searchMode])
        c = connection.cursor()

        if category:
            clause = "WHERE ("
            clauseList = [clause,]
            substitutes = []
            catCount = 1
            headerCount = 1
            
            for header in category:
                if 1 < headerCount:
                    clauseList.append(" AND (")

                try:
                    splitCategory = unicode(bytes(category[header]), "utf-8").split(splitter)
                except TypeError:
                    ## Python 3
                    splitCategory = unicode(bytes(category[header], "utf-8"), "utf-8").split(splitter)

                for cat in splitCategory:
                    if 1 < catCount:
                        clauseList.append(" OR")

                    if searchMode in self.SEARCH_FUNCTIONS:
                        clauseList.append("{} REGEXP(?)".format(clean(header)))
                    else:
                        clauseList.append("{}=?".format(clean(header)))
                    substitutes.append(cat)

                    catCount += 1
                    
                clauseList.append(")")
                headerCount += 2
                catCount = 1

            clause = "".join(clauseList)

            statement = "SELECT id FROM {} {}".format(table, clause)
            logger.debug("(get_ids) Substitutes: {}".format(substitutes))
            logger.debug("(get_ids) SQLite statement: {}".format(statement))

            c.execute(statement, substitutes)
        else:
            c.execute("SELECT id FROM {}".format(table))

        ids = c.fetchall()

        return ids

    def random_line(self, header, table, category=None, searchMode="", splitter=","):
        """
        Chooses a random line from the table under the header.

        Args:
            header(unicode): The header of the column where you want a random line from.
            table(unicode): Name of the table to look into.
            category(dict, optional): Categories you want to filter the line by, formatted like so:
                {"header of categories 1": "category1,category2", "header of category 2": "category3"}
                Multiple categories under a single header are separated with a comma.
            searchMode(unicode, optional): Determines the method of searching for matches.
                Database.SEARCH_SIMPLE ("simple) uses match_dumbsimple function.
                Database.SEARCH_REGEX ("regex") uses regexp function.
                Database.SEARCH_DUMBREGEX ("dumbregex") uses match_dumbregex function.
                Any other value uses a strict search.
            splitter(unicode, optional): What separates multiple categories (default is a comma).

        Returns:
            line(unicode): A random line from the database.

        Raises:
            OperationalError: If header or table doesn't exist.
            TypeError: If category is neither None nor a dictionary.

        Examples:
            >>> random_line("line", {"type": "greeting"})
            Hello.
        """
        header = clean(header)
        table = clean(table)
        line = ""
        
        connection = sqlite3.connect(self.db)
        c = connection.cursor()

        if category:
            ids = self.get_ids(table, category, searchMode, splitter)
            if ids:
                line = random.choice(ids)
                line = self.get_field(line, header, table)
            else:
                line = ""
        else:
            c.execute("SELECT {} FROM {} ORDER BY Random() LIMIT 1".format(header, table))  # TODO: Take categories into account.
            line = c.fetchone()[0]

        return line


class Singalong(Database):
    def __init__(self, inputFile, songFile):
        super(type(self), self).__init__(self, inputFile)
        self.lineNum = 0
        self.song = None
        self.songFile = Database(songFile)

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
        

def test_sql():
    pass
    
    
if "__main__" == __name__:
    test_sql()

