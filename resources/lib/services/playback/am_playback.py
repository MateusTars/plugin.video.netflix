# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Smeulf (original implementation module)
    Operations for changing the playback status

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time

import xbmc

import resources.lib.common as common
from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .action_manager import ActionManager

try:  # Kodi >= 19
    from xbmcvfs import translatePath  # pylint: disable=ungrouped-imports
except ImportError:  # Kodi 18
    from xbmc import translatePath  # pylint: disable=ungrouped-imports


class AMPlayback(ActionManager):
    """Operations for changing the playback status"""

    SETTING_ID = 'ResumeManager_enabled'

    def __init__(self):
        super(AMPlayback, self).__init__()
        self.resume_position = None
        self.enabled = True
        self.start_time = None
        self.is_player_in_pause = False
        self.is_played_from_strm = False
        self.credits_offset = None

    def __str__(self):
        return 'enabled={}'.format(self.enabled)

    def initialize(self, data):
        # Due to a bug on Kodi the resume on SRTM files not works correctly, so we force the skip to the resume point
        self.resume_position = data.get('resume_position')
        self.is_played_from_strm = data['is_played_from_strm']
        self.credits_offset = data['metadata'][0].get('creditsOffset')

    def on_playback_started(self, player_state):
        if self.resume_position:
            LOG.info('AMPlayback has forced resume point to {}', self.resume_position)
            xbmc.Player().seekTime(int(self.resume_position))

    def on_tick(self, player_state):
        # Stops playback when paused for more than one hour.
        # Some users leave the playback paused also for more than 12 hours,
        # this complicates things to resume playback, because the manifest data expires and with it also all
        # the streams urls are no longer guaranteed, so we force the stop of the playback.
        if self.is_player_in_pause and (time.time() - self.start_time) > 3600:
            LOG.info('The playback has been stopped because it has been exceeded 1 hour of pause')
            common.stop_playback()

    def on_playback_pause(self, player_state):
        self.start_time = time.time()
        self.is_player_in_pause = True

    def on_playback_resume(self, player_state):
        self.is_player_in_pause = False

    def on_playback_stopped(self, player_state):
        # In the case of the episodes, it could happen that Kodi does not assign as watched a video,
        # this because the credits can take too much time, then the breaking point of the video
        # falls in the part that kodi recognizes as unwatched (playcountminimumpercent 90% + no-mans land 2%)
        # https://kodi.wiki/view/HOW-TO:Modify_automatic_watch_and_resume_points#Settings_explained
        # In these cases we change/fix manually the watched status of the video
        if not self.videoid.mediatype == common.VideoId.EPISODE or int(player_state['percentage']) > 92:
            return
        if not self.credits_offset or not player_state['elapsed_seconds'] >= self.credits_offset:
            return
        if G.ADDON.getSettingBool('ProgressManager_enabled') and not self.is_played_from_strm:
            # This have not to be applied with our custom watched status of Netflix sync, within the addon
            return
        if self.is_played_from_strm:
            # The current video played is a STRM, then generate the path of a STRM file
            file_path = G.SHARED_DB.get_episode_filepath(
                self.videoid.tvshowid,
                self.videoid.seasonid,
                self.videoid.episodeid)
            url = G.py2_decode(translatePath(file_path))
            if G.KODI_VERSION.is_major_ver('18'):
                common.json_rpc('Files.SetFileDetails',
                                {"file": url, "media": "video", "resume": {"position": 0, "total": 0}, "playcount": 1})
                # After apply the change Kodi 18 not update the library directory item
                common.container_refresh()
            else:
                common.json_rpc('Files.SetFileDetails',
                                {"file": url, "media": "video", "resume": None, "playcount": 1})
        else:
            if G.KODI_VERSION.is_major_ver('18'):
                # "Files.SetFileDetails" on Kodi 18 not support "plugin://" path
                return
            url = common.build_url(videoid=self.videoid,
                                   mode=G.MODE_PLAY,
                                   params={'profile_guid': G.LOCAL_DB.get_active_profile_guid()})
            common.json_rpc('Files.SetFileDetails',
                            {"file": url, "media": "video", "resume": None, "playcount": 1})
        LOG.debug('Has been fixed the watched status of the video: {}', url)
