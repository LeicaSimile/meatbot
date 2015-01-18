import ConfigParser
import os.path
import random
import re
from string import maketrans

DIR_DATABASE = os.path.join(os.path.dirname(__file__), "database")
DIR_LOG = os.path.join(os.path.dirname(__file__), "log")


class Settings(object):
    """ Convenient way to access config file's values (via dictionary). """
    def __init__(self, inputFile=os.path.join(DIR_DATABASE, "Settings.ini")):
        self.inputFile = inputFile
        self.keywords = {}
        
        self.read_file()

    def read_file(self):
        parser = ConfigParser.ConfigParser()
        parser.read(self.inputFile)

        for section in parser.sections():
           self.keywords[section] = {}
           for tup in parser.items(section):
               self.keywords[section][tup[0]] = ""
               self.keywords[section][tup[0]] = tup[1].decode("string-escape")


class LineParser(object):
    """
    For reading lines in a plain text file and mapping the fields according to primary key and given headers.
    """
    _lines = {}
    _categories = {}
    keyIsNumeric = True
    
    def __init__(self, inputFile=os.path.join(DIR_DATABASE, "chatting.txt"), primaryKey="id"):
        self.inputFile = inputFile
        self.settings = Settings().keywords
        self.key = primaryKey

    def read_file(self):
        """
        Reads the input file and stores the lines, sorted by category and by the primary key.
        """
        ## Assuming the first line contains the headers.
        headers = []
        lineFields = []
        
        with open(self.inputFile, "r") as data:
            index = 0
            for line in data:
                line = line.strip("\n")
                if 0 == index:
                    ## Read headers.
                    headers = line.split(self.settings["Splitters"]["field"])
                    for header in headers:
                        if self.key != header:
                            self._categories[header] = {}
                else:
                    ## Read entries under headers.
                    lineFields = line.split(self.settings["Splitters"]["field"])

                    currentKey = lineFields[headers.index(self.key)]
                    if self.keyIsNumeric:
                        try:
                            currentKey = int(lineFields[headers.index(self.key)])
                        except ValueError:
                            currentKey = lineFields[headers.index(self.key)]
                            self.keyIsNumeric = False

                    self._lines[currentKey] = {}

                    for header in headers:
                        if self.key != header:
                            try:
                                entry = lineFields[headers.index(header)]
                            except IndexError:
                                entry = ""  # Current field was left out - assume a blank entry.
                                
                            self._lines[currentKey][header] = entry

                            if entry in self._categories[header]:
                                self._categories[header][entry].append(currentKey)
                            else:
                                self._categories[header][entry] = [currentKey,]

                index += 1

    def parse_choices(self, stringParse):
        """
        Chooses a random option in a given set.

        Args:
            stringParse(str): String to parse. Options are enclosed in angle brackets, separated by a pipeline.

        Yields:
            newString(str): An option from the rightmost set of options is chosen for the string and updates accordingly.

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
        
        choice = ""
        openChar = self.settings["Blocks"]["openchoose"]
        closeChar = self.settings["Blocks"]["closechoose"]
        newString = stringParse

        while openChar in stringParse and closeChar in stringParse:
            stringParse = newString
            openIndex = 0
            closeIndex = 0
            
            openIndex = stringParse.rfind(openChar)
            while closeIndex <= openIndex:
                closeIndex = stringParse.find(closeChar, closeIndex + 1)
                
            tmpBlock = stringParse[openIndex:closeIndex + 1]
            if tmpBlock:
                newString = (stringParse[:openIndex] + random.choice(tmpBlock.replace(openChar, "").replace(closeChar, "").split(self.settings["Splitters"]["parseoptions"])) +
                             stringParse[closeIndex + 1:])

            yield newString
        
    def parse_optional(self, stringParse):
        """
        Chooses whether to omit a substring or not.

        Args:
            stringParse(str): String to parse. Substring to be reviewed is enclosed in braces.

        Yields:
            stringParse(str): The string with or without the rightmost substring, stripped of the braces.

        Raises:
            StopIteration: stringParse's braces are fully parsed.

        Examples:
            >>> next(parse_optional("You're mean{ingful}."))
            "You're meaningful."

            >>> result = parse_optional("You're pretty{{ darn} awful}.")
            >>> for _ in result: print(next(result))
            You're pretty{ darn awful}.
            You're pretty.
        """
        
        choice = ""
        openChar = self.settings["Blocks"]["openomit"]
        closeChar = self.settings["Blocks"]["closeomit"]
        newString = stringParse

        while openChar in stringParse and closeChar in stringParse:
            stringParse = newString
            openIndex = 0
            closeIndex = 0

            openIndex = stringParse.rfind(openChar)
            while closeIndex <= openIndex:
                closeIndex = stringParse.find(closeChar, closeIndex + 1)
                
            tmpBlock = stringParse[openIndex:closeIndex + 1]
            if tmpBlock:
                if random.getrandbits(1):
                    newString = stringParse[:openIndex] + stringParse[closeIndex + 1:]
                else:
                    newString = stringParse[:openIndex] + stringParse[openIndex + 1:closeIndex] + stringParse[closeIndex + 1:]
            else:
                return

            yield newString

    def parse_all(self, stringParse):
        """
        Combines parse_choices() with parse_optional().

        Args:
            stringParse(str): String to parse.

        Returns:
            stringParse(str): Updated string.

        Examples:
            >>> parse_all("I'm {b}eating you{r <cake|homework>}.")
            I'm eating your homework.
        """
        
        for generator in (self.parse_optional, self.parse_choices):
            result = generator(stringParse)
            for _ in result:
                stringParse = next(result)

        return stringParse

    def dumb_down(self, line):
        """ Simple way to "dumb" a string down to make matching less strict. """
        line = line.rstrip(" ,.!?-")
        line = line.strip()
        line = re.sub(r"\W", "", line.replace(" ", "_"))
        while "__" in line:
            line = line.replace("__", "_").strip("_ ")
            
        return line

    def dumb_regex(self, line, willCompile=True):
        """
        Makes matching a line to be much more permissive.
        With withCompile as True, it will return a regex object,
        else a regular string. Meant to be used for pattern matching.
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


    def get_column(self, header, maximum=None):
        """
        Gets fields under a column header. The order the fields were entered in might not be preserved.

        Args:
            header(str): Name of column's header.
            maximum(int, optional): Maximum amount of fields to fetch.

        Returns:
            fields(list): List of fields under header.
        """
        fields = []
        if header in self._categories:
            fields = [f for f in self._categories[header] if f not in fields]
            if isinstance(maximum, int) and maximum < len(fields):
                fields = fields[:maximum]
                print(maximum, len(fields))
        
        return fields

    def get_keys(self, category=None):
        """
        Gets the keys that fit within the specified categories. Gets all keys if category is None.

        Args:
            category(dict, optional): Categories you want to filter the line by.
                {"header of categories 1": "category1,category2", "header of category 2": "category3"}
                Multiple categories under a single header are separated with a comma.

        Returns:
            keys(list): List of keys that match the categories.

        Examples:
            >>> get_keys({"type": "greeting"})
            [1, 2, 3, 5, 9, 15]
        """
        
        keys = self._lines.keys()
        if category:
            for header in category:
                if header in self._categories:
                    cats = category[header].split(",")

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

    def substitute(self, line, variables=None):
        """
        Substitutes values in a single line.
        """
        if isinstance(variables, dict):
            for var in variables:
                line.replace(var, variables[var])

        line = "".join(line.replace(self.init["Variables"]["action"], "\001ACTION"), "\001")

        return line


class Singalong(LineParser):
    def __init__(self, inputFile=os.path.join(DIR_DATABASE, "singalong.txt"), primaryKey="id"):
        LineParser.__init__(self, inputFile, primaryKey)
        self.lineNum = 0
        self.title = ""

    def get_matches(self, query):
        matches = []
        
        return matches

    def next_line(self, auto=False):
        line = ""

        return line


def test_parser():
    x = LineParser()
    x.read_file()
    print(x.parse_all("Stop {b}eating <my|your{ dog's}> new <highsc<ore|hool>|record{ing{ tape}}>."))
    print(x.random_line("line"))
    print(x.dumb_regex("Hello?!. Hello because whoa", False))

if "__main__" == __name__:
    test_parser()
