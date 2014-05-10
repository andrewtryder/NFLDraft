###
# Copyright (c) 2014, spline
# All rights reserved.
#
#
###
# my libs
from base64 import b64decode
import cPickle as pickle
from BeautifulSoup import BeautifulSoup
import re
# extra supybot libs
import supybot.conf as conf
import supybot.schedule as schedule
import supybot.ircmsgs as ircmsgs
# supybot libs
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('NFLDraft')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x:x

class NFLDraft(callbacks.Plugin):
    """Add the help for "@plugin help NFLDraft" here
    This should describe *how* to use this plugin."""
    threaded = True

    def __init__(self, irc):
        self.__parent = super(NFLDraft, self)
        self.__parent.__init__(irc)
        # initial states for channels.
        self.channels = {} # dict for channels with values as teams/ids
        self._loadpickle() # load saved data.
        # initial states for games.
        self.draft = None
        self.nextcheck = None
        # url for draft.
        self.url = b64decode('aHR0cDovL3d3dy5zcG90cmFjLmNvbS9kcmFmdC10cmFja2VyL25mbC8=')
        if not self.draft:
            self.draft = self._fetchdraft()
        # now schedule our events.
        def checkdraftcron():
            self.checkdraft(irc)
        try: # check scores.
            schedule.addPeriodicEvent(checkdraftcron, self.registryValue('checkInterval'), now=False, name='checkdraft')
        except AssertionError:
            try:
                schedule.removeEvent('checkdraft')
            except KeyError:
                pass
            schedule.addPeriodicEvent(checkdraftcron, self.registryValue('checkInterval'), now=False, name='checkdraft')

    def die(self):
        try:
            schedule.removeEvent('checkdraft')
        except KeyError:
            pass
        self.__parent.die()


    ######################
    # INTERNAL FUNCTIONS #
    ######################

    def _httpget(self, url):
        """General HTTP resource fetcher. Pass headers via h, data via d, and to log via l."""

        l = False
        if self.registryValue('logURLs') or l:
            self.log.info(url)

        try:
            h = {"User-Agent":"Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:17.0) Gecko/20100101 Firefox/17.0"}
            page = utils.web.getUrl(url, headers=h)
            return page
        except Exception, e:
            self.log.error("_httpget: ERROR opening {0} message: {1}".format(url, e))
            return None

    ###########################################
    # INTERNAL CHANNEL POSTING AND DELEGATION #
    ###########################################

    def _post(self, irc, message):
        """Posts message to a specific channel."""

        # first check if we have channels.
        if len(self.channels) == 0: # bail if none.
            return
        # we do have channels. lets go and check where to put what.
        postchans = [k for (k, v) in self.channels.items() if v == 1] # only channels with 1 = on.
        # iterate over each and post.
        for postchan in postchans:
            try:
                irc.queueMsg(ircmsgs.privmsg(postchan, message))
            except Exception as e:
                self.log.info("_post :: ERROR :: Could not send {0} to {1}. {2}".format(message, postchan, e))

    ##############################
    # INTERNAL CHANNEL FUNCTIONS #
    ##############################

    def _loadpickle(self):
        """Load channel data from pickle."""

        try:
            datafile = open(conf.supybot.directories.data.dirize(self.name()+".pickle"), 'rb')
            try:
                dataset = pickle.load(datafile)
            finally:
                datafile.close()
        except IOError:
            return False
        # restore.
        self.channels = dataset["channels"]
        return True

    def _savepickle(self):
        """Save channel data to pickle."""

        data = {"channels": self.channels}
        try:
            datafile = open(conf.supybot.directories.data.dirize(self.name()+".pickle"), 'wb')
            try:
                pickle.dump(data, datafile)
            finally:
                datafile.close()
        except IOError:
            return False
        return True

    ####################
    # FETCH OPERATIONS #
    ####################

    def _fetchdraft(self):
        """Returns the draft stuff."""

        url = self.url
        html = self._httpget(url)
        if not html:
            self.log.error("ERROR: _fetchdraft :: could not fetch {0} :: {1}".format(url))
            return None
        # try/except for this
        try:
            soup = BeautifulSoup(html)
            # find all rows with ids that are numbers.
            plyrs = soup.findAll('tr', attrs={'id':re.compile('^\d.*?')})
            # empty container.
            d = {}
            # enumerate over these rows.
            for (i, p) in enumerate(plyrs):
                # find all tds.
                partds = p.findAll('td')
                #self.log.info("PARTDS: {0}".format(partds))
                pick = partds[0]
                pick = pick.getText().encode('utf-8')
                tm = partds[1]
                tm = tm.getText(separator=' ').encode('utf-8')
                plr = partds[2]
                plr = plr.getText().encode('utf-8')
                pos = partds[3]
                pos = pos.getText().encode('utf-8')
                # now, lets append.
                d[i] = {'pick':pick, 'plr':plr, 'pos':pos, 'tm':tm}
            # return d
            return d
        except Exception, e:
            self.log.info("_fetchdraft :: ERROR :: {0}".format(e))
            return None

    #############################
    # PUBLIC CHANNEL OPERATIONS #
    #############################

    def draftchannel(self, irc, msg, args, op, optchannel):
        """<add #channel|del #channel|list>

        Add or delete a channel from draft output.
        Use list to list channels we output to.
        Ex: add #channel OR del #channel OR list
        """

        # first, lower operation.
        op = op.lower()
        # next, make sure op is valid.
        validop = ['add', 'list', 'del']
        if op not in validop: # test for a valid operation.
            irc.reply("ERROR: '{0}' is an invalid operation. It must be be one of: {1}".format(op, " | ".join([i for i in validop])))
            return
        # if we're not doing list (add or del) make sure we have the arguments.
        if (op != 'list'):
            if not optchannel:
                irc.reply("ERROR: add and del operations require a channel and team. Ex: add #channel or del #channel")
                return
            # we are doing an add/del op.
            optchannel = optchannel.lower()
            # make sure channel is something we're in
            if optchannel not in irc.state.channels:
                irc.reply("ERROR: '{0}' is not a valid channel. You must add a channel that we are in.".format(optchannel))
                return
        # main meat part.
        # now we handle each op individually.
        if op == 'add': # add output to channel.
            self.channels[optchannel] = 1 # add it and on.
            self._savepickle() # save.
            irc.reply("I have enabled draft status updates on {0}".format(optchannel))
        elif op == 'list': # list channels
            if len(self.channels) == 0: # no channels.
                irc.reply("ERROR: I have no active channels defined. Please use the draftchannel add operation to add a channel.")
            else: # we do have channels.
                for (k, v) in self.channels.items(): # iterate through and output translated keys.
                    if v == 0: # swap 0/1 into OFF/ON.
                        irc.reply("{0} :: OFF".format(k))
                    elif v == 1:
                        irc.reply("{0} :: ON".format(k))
        elif op == 'del': # delete an item from channels.
            if optchannel in self.channels: # id is already in.
                del self.channels[optchannel] # remove it.
                self._savepickle() # save.
                irc.reply("I have successfully removed {0}".format(optchannel))
            else: # id was NOT in there.
                irc.reply("ERROR: I do not have {0} in {1}".format(optarg, optchannel))

    draftchannel = wrap(draftchannel, [('checkCapability', 'admin'), ('somethingWithoutSpaces'), optional('channel')])

    def drafton(self, irc, msg, args, channel):
        """
        Enable draft announcing in channel.
        """

        # channel
        channel = channel.lower()
        # check if op.
        if not irc.state.channels[channel].isOp(msg.nick):
            irc.reply("ERROR: You must be an op in this channel for this command to work.")
            return
        # check now.
        if channel in self.channels:
            self.channels[channel] = 1
            irc.reply("I have turned on draft livescoring for {0}".format(channel))
        else:
            irc.reply("ERROR: {0} is not in any known channels.".format(channel))

    drafton = wrap(drafton, [('channel')])

    def draftoff(self, irc, msg, args, channel):
        """
        Disable draft announcing in channel.
        """

        # channel
        channel = channel.lower()
        # check if op.
        if not irc.state.channels[channel].isOp(msg.nick):
            irc.reply("ERROR: You must be an op in this channel for this command to work.")
            return
        # check now.
        if channel in self.channels:
            self.channels[channel] = 0
            irc.reply("I have turned off draft livescoring for {0}".format(channel))
        else:
            irc.reply("ERROR: {0} is not in any known channels.".format(channel))

    draftoff = wrap(draftoff, [('channel')])

    #################
    # MAIN FUNCTION #
    #################

    #def checkdraft(self, irc, msg, args):
    def checkdraft(self, irc):
        """Main handling function."""

        self.log.info("checkdraft: starting check.")
        # first, we need a baseline set of games.
        if not self.draft: # we don't have them if reloading.
            self.log.info("checkdraft: I do not have any draft. Fetching initial draft.")
            self.draft = self._fetchdraft()
        # verify we have a baseline.
        if not self.draft: # we don't. must bail.
            self.log.info("checkdraft: after second try, I could not get self.draft.")
            return
        else: # we have games. setup the baseline stuff.
            draft1 = self.draft # games to compare from.
        # now, we must grab new games. if something goes wrong or there are None, we bail.
        draft2 = self._fetchdraft()
        if not draft2: # if something went wrong, we bail.
            self.log.info("checkdraft: I was unable to get new draft.")
            return
        # what we'll do is iterate through the list of dicts.
        # d is stored. new d is compared.
        # we iterate through each item and look if "plr" changes.
        # if plr changes, it means someone was picked.
        # we then announce the "pick" and also announce what pick/team is next.
        for (k, v) in draft1.items():  # {'rd': rd, 'pick':pick, 'plr':plr, 'col':col, 'pos':pos, 'tm':tm }
            if v['plr'] != draft2[k]['plr']:  # plr changed. that means pick is in.
                mstr = "Pick: {0} :: {1} has picked {2}, {3}".format(ircutils.bold(v['pick']), ircutils.bold(draft2[k]['tm']), ircutils.underline(draft2[k]['plr']), draft2[k]['pos'])
                self._post(irc, mstr)
                # figure out who picks next.
                nextpick = k+1  # this is the number(int) + 1.
                if nextpick > 255:  # this means the draft is over.
                    self.log.info("checkdraft: pick is {0}. we have reached the end of the draft.".format(nextpick))
                else:  # we're not at the last pick.
                    n = draft2[nextpick]  # easier to access. {'rd': rd, 'pick':pick, 'plr':plr, 'col':col, 'pos':pos, 'tm':tm }
                    self.log.info("n = {0}".format(n))
                    np = "{0} is now on the clock with the {1} pick".format(n['tm'], n['pick'])
                    self._post(irc, np)
            
        # now that we're done checking changes, copy the new into self.games to check against next time.
        self.draft = draft2
        self.log.info("checkdraft: done checking. copied.")
        
Class = NFLDraft


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
