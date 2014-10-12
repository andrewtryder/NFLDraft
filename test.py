###
# Copyright (c) 2014, spline
# All rights reserved.
#
#
###

from supybot.test import *

class NFLDraftTestCase(PluginTestCase):
    plugins = ('NFLDraft',)
    
    def testNFLDraft(self):
        self.assertNotError('draftchannel add #test')
        self.assertNotError('draftchannel del #test')


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
