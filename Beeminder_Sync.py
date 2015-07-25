# -*- coding: utf-8 -*-
# by: muflax <mail@muflax.com>, 2012

# This add-on sends your review stats to Beeminder (beeminder.com) and so keeps
# your graphs up-to-date.
#
# Experimental! Use at your own risk.
#
# 1. Create goal at Beeminder.
# 2. Use type Odometer.
# 3. Set variables in add-on file.
# 4. Review!
# 5. Sync to AnkiWeb.
from anki.hooks import wrap, addHook
from aqt.reviewer import Reviewer
from anki.sched import Scheduler
from anki.sync import Syncer
from aqt.main import AnkiQt
from aqt import *
from aqt.utils import showInfo, openLink
import anki.sync

import datetime
import httplib, urllib, os, sys, json
####################################################
# Adjust these variables to your beeminder config. #
####################################################
# Login Info
#ACCOUNT = "" # beeminder account name
#TOKEN   = ""   # available at <https://www.beeminder.com/api/v1/auth_token.json>

# Goal names - Set either to "" if you don't use this kind of goal. The name is the short part in the URL.
#REP_GOAL = "" # Goal for total reviews / day, e.g. "anki" if your goal is called "anki".
#NEW_GOAL = ""     # goal for new cards / day, e.g. "anki-new".

# Offsets - Skip that many earlier reps so your graph can start at 0 (for old decks - set to 0 if unsure).
REP_OFFSET = 0
NEW_OFFSET = 0
Syncer.beeminder_configured = False

#####################
# Code starts here. #
#####################

# Debug - Skip this.
SEND_DATA = True # set to True to actually send data

config ={}
conffile = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".beeminder.conf")
conffile = conffile.decode(sys.getfilesystemencoding())

def internet_on():
    try:
        response=urllib2.urlopen('http://beeminder.com',timeout=1)
        return True
    except urllib2.URLError as err: pass
    return False

    #Read values from file if it exists
if os.path.exists(conffile): # Load config file
    config = json.load(open(conffile, 'r'))
    TOKEN = config['token']
    ACCOUNT = config['user']
    REP_GOAL = config['rep_goal']
    NEW_GOAL = config['new_goal']
    Syncer.beeminder_configured = True

#Setup menu to configure Beeminder userid and api key
def setup():
    global config
    if os.path.exists(conffile):
        config = json.load(open(conffile, 'r'))
        TOKEN = config['token']
        ACCOUNT = config['user']
        REP_GOAL = config['rep_goal']
        NEW_GOAL = config['new_goal']
        
    ACCOUNT, ok = utils.getText("Enter your user ID:")
    if ok == True:
        TOKEN, ok = utils.getText('Enter your API token:')
        if ok == True: # Create config file and save values
                REP_GOAL, ok = utils.getText("Enter your goal for total review:")
                if ok == True:
                    NEW_GOAL, ok = utils.getText("Enter your goal for new review:(optional)")
                    if ok == True:
                        TOKEN = str(TOKEN)
                        ACCOUNT = str(ACCOUNT)
                        REP_GOAL = str(REP_GOAL)
                        NEW_GOAL = str(NEW_GOAL)
                        config['user'] = ACCOUNT
                        config['token'] = TOKEN
                        config['rep_goal'] = REP_GOAL
                        config['new_goal'] = NEW_GOAL
                        json.dump( config, open( conffile, 'w' ) )
                        Syncer.beeminder_configured = True
                        utils.showInfo("The add-on has been setup.")
                    if ok == False:
                        TOKEN = str(api_token)
                        ACCOUNT = str(user_id)
                        REP_GOAL = str(REP_GOAL)
                        config['user'] = ACCOUNT
                        config['token'] = TOKEN
                        config['rep_goal'] = REP_GOAL
                        json.dump( config, open( conffile, 'w' ) )
                        Syncer.beeminder_configured = True
                        utils.showInfo("The add-on has been setup.")

#Add Setup to menubar
action = QAction("Setup Beeminder", mw)
mw.connect(action, SIGNAL("triggered()"), setup)
mw.form.menuTools.addAction(action)

def checkCollection(col=None, force=False):
    """Check for unreported cards and send them to beeminder."""
    col = col or mw.col
    if col is None:
        return

    # reviews
    if Syncer.beeminder_configured == True:
        if REP_GOAL:
            reps           = col.db.first("select count() from revlog")[0]
            last_timestamp = col.conf.get("beeminderRepTimestamp", 0)
            timestamp      = col.db.first("select id/1000 from revlog order by id desc limit 1")
            if timestamp is not None:
                timestamp = timestamp[0]
            reportCards(col, reps, timestamp, "beeminderRepTotal", REP_GOAL, REP_OFFSET)

            if (force or timestamp != last_timestamp) and SEND_DATA:
                col.conf["beeminderRepTimestamp"] = timestamp
                col.setMod()

    # new cards
    if Syncer.beeminder_configured == True:
        if NEW_GOAL:
            new_cards      = col.db.first("select count(distinct(cid)) from revlog where type = 0")[0]
            last_timestamp = col.conf.get("beeminderNewTimestamp", 0)
            timestamp      = col.db.first("select id/1000 from revlog where type = 0 order by id desc limit 1")
            if timestamp is not None:
                timestamp = timestamp[0]
            reportCards(col, new_cards, timestamp, "beeminderNewTotal", NEW_GOAL, NEW_OFFSET)

            if (force or timestamp != last_timestamp) and SEND_DATA:
                col.conf["beeminderNewTimestamp"] = timestamp
                col.setMod()
    if Syncer.beeminder_configured == True:
        if force and (REP_GOAL or NEW_GOAL):
            showInfo("Synced with Beeminder.")

def reportCards(col, total, timestamp, count_type, goal, offset=0, force=False):
    """Sync card counts and send them to beeminder."""

    if not SEND_DATA:
        print "type:", count_type, "count:", total

    # get last count and new total
    last_total = col.conf.get(count_type, 0)
    total      = max(0, total - offset)

    if not force and (total <= 0 or total == last_total):
        if not SEND_DATA:
            print "nothing to report..."
        return

    if total < last_total: #something went wrong
        raise Exception("Beeminder total smaller than before")

    # build data
    date = "%d" % timestamp
    comment = "anki update (+%d)" % (total - last_total)
    data = {
        "date": date,
        "value": total,
        "comment": comment,
    }

    if SEND_DATA:
        account = ACCOUNT
        token = TOKEN
        sendApi(ACCOUNT, TOKEN, goal, data)
        col.conf[count_type] = total
    else:
        print "would send:"
        print data

def sendApi(account, token, goal, data):
    base = "www.beeminder.com"
    cmd = "datapoints"
    api = "/api/v1/users/%s/goals/%s/%s.json" % (account, goal, cmd)

    headers = {"Content-type": "application/x-www-form-urlencoded",
               "Accept": "text/plain"}

    params = urllib.urlencode({"timestamp": data["date"],
                               "value": data["value"],
                               "comment": data["comment"],
                               "auth_token": token})

    conn = httplib.HTTPSConnection(base)
    conn.request("POST", api, params, headers)
    response = conn.getresponse()
    if not response.status == 200:
        raise Exception("transmission failed:", response.status, response.reason, response.read())
    conn.close()

def beeminderUpdate(obj, _old=None):
    ret = _old(obj)
    col = mw.col or mw.syncer.thread.col
    if col is not None:
        checkCollection(col)

    return ret

# convert time to timestamp because python sucks
def timestamp(time):
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = time - epoch
    timestamp = "%d" % delta.total_seconds()
    return timestamp

# run update whenever we sync a deck
anki.sync.Syncer.sync = wrap(anki.sync.Syncer.sync, beeminderUpdate, "around")
