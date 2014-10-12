###
# Copyright (c) 2014, spline
# All rights reserved.
#
#
###

from supybot.test import *

class NFLDraftTestCase(ChannelPluginTestCase):
    plugins = ('NFLDraft',)
    
    def testNFLDraft(self):
        self.assertResponse('draftchannel add #test', "I have enabled draft status updates on #test")
        self.assertResponse('draftchannel del #test', "I have successfully removed #test")


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
