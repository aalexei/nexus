import subprocess, re
from pathlib import Path
import json

import logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)


def osascript(script):
    """
    Run an osa script and grab the output
    """
    output = subprocess.check_output(["osascript","-e",script])
    output = output.decode("utf-8").strip()
    return output



def addPDFtoInbox(path, title=None, tags=[]):
    script = '''
    tell application id "DNtp"

    set theDestination to incoming group of database named "Test_devon_share"
    set output to ""

    set thisRecord to create PDF document from "file:///{path}" in theDestination without pagination
    if exists thisRecord then
        set output to uuid of thisRecord
        tell thisRecord
            set name to "{title}"
            set tags to "{tags}"
        end tell
    end if

    return output
    end tell 
    '''

    output = osascript(script.format(
                        path=Path('aaa.pdf').resolve(),
                        title = "The solution to everything",
                        tags = ";".join(set(["Good","Measurement"]))
                        ))

    return output

def getInfo(uuid):
    """
    Get the meta-data for an item given the item's uuid
    """
    script = '''
    tell application id "DNtp"
        set this_item to (get record with uuid "{uuid}")

        set out to "kind: " & (the kind of this_item) & "\n"
        set out to out & "mime:" & (MIME type of this_item) & "\n"
        set out to out & "name:" & (the name of this_item) & "\n"
        set out to out & "url:" & (the URL of this_item) & "\n"
        set out to out & "path:" & (the path of this_item) & "\n"
        set out to out & "cdate:" & (the creation date of this_item) & "\n"
        set out to out & "mdate:" & (the modification date of this_item) & "\n"

        return out
    end tell 
    '''

    # don't grab the source, if it's binary or a web page it will be a mess
    # set out to out & "source:" & (the source of this_item) & "\n"


    output = osascript(script.format(uuid=uuid))

    info = {}
    for line in output.split('\n'):
        key,value = line.split(':', maxsplit=1)
        info[key] = value.strip()

    return info



def getBEinfo(uuid):
    script = '''
    tell application "Bookends"
        return «event ToySRJSN» "{uuid}" given string:"type,authors,thedate,pages,title,journal" 
    end tell
    '''

    output = osascript(script.format(uuid=uuid))
    try:
        data = json.loads(output)
        if len(data)>0:
            data = data[0]
            return data
        else:
            return {'error': True}

    except json.decoder.JSONDecodeError:
        return {'error': True}

if __name__ == '__main__':
    pass


