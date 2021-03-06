# This file is part of SickRage.
#
# URL: https://www.sickrage.tv
# Git: https://github.com/SiCKRAGETV/SickRage.git
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import sickbeard

from datetime import date, timedelta
from sickbeard.common import IGNORED, Quality, WANTED, UNAIRED
from sickbeard.db import DBConnection
from sickbeard.network_timezones import parse_date_time
from sickbeard.sbdatetime import sbdatetime
from sickrage.helper.common import dateFormat, timeFormat
from sickrage.helper.quality import get_quality_string


class ComingEpisodes:
    """
    Missed:   yesterday...(less than 1 week)
    Today:    today
    Soon:     tomorrow till next week
    Later:    later than next week
    """
    categories = ['later', 'missed', 'soon', 'today']
    sorts = {
        'date': (lambda a, b: cmp(a[b'localtime'], b[b'localtime'])),
        'network': (lambda a, b: cmp((a[b'network'], a[b'localtime']), (b[b'network'], b[b'localtime']))),
        'show': (lambda a, b: cmp((a[b'show_name'], a[b'localtime']), (b[b'show_name'], b[b'localtime']))),
    }

    def __init__(self):
        pass

    @staticmethod
    def get_coming_episodes(categories, sort, group, paused=sickbeard.COMING_EPS_DISPLAY_PAUSED):
        """
        :param categories: The categories of coming episodes. See ``ComingEpisodes.categories``
        :param sort: The sort to apply to the coming episodes. See ``ComingEpisodes.sorts``
        :param group: ``True`` to group the coming episodes by category, ``False`` otherwise
        :param paused: ``True`` to include paused shows, ``False`` otherwise
        :return: The list of coming episodes
        """

        if not isinstance(categories, list):
            categories = categories.split('|')

        if sort not in ComingEpisodes.sorts.keys():
            sort = 'date'

        today = date.today().toordinal()
        next_week = (date.today() + timedelta(days=7)).toordinal()
        recently = (date.today() - timedelta(days=sickbeard.COMING_EPS_MISSED_RANGE)).toordinal()
        qualities_list = Quality.DOWNLOADED + Quality.SNATCHED + Quality.SNATCHED_BEST + Quality.SNATCHED_PROPER + Quality.ARCHIVED + [
            IGNORED]

        db = DBConnection()
        fields_to_select = ', '.join(
                ['airdate', 'airs', 'description', 'episode', 'imdb_id', 'e.indexer', 'indexer_id', 'name', 'network',
                 'paused', 'quality', 'runtime', 'season', 'show_name', 'showid', 's.status']
        )
        results = db.select(
                'SELECT %s ' % fields_to_select +
                'FROM tv_episodes e, tv_shows s '
                'WHERE season != 0 '
                'AND airdate >= ? '
                'AND airdate < ? '
                'AND s.indexer_id = e.showid '
                'AND e.status NOT IN (' + ','.join(['?'] * len(qualities_list)) + ')',
                [today, next_week] + qualities_list
        )

        done_shows_list = [int(result[b'showid']) for result in results]
        placeholder = ','.join(['?'] * len(done_shows_list))
        placeholder2 = ','.join(
            ['?'] * len(Quality.DOWNLOADED + Quality.SNATCHED + Quality.SNATCHED_BEST + Quality.SNATCHED_PROPER))

        results += db.select(
                'SELECT %s ' % fields_to_select +
                'FROM tv_episodes e, tv_shows s '
                'WHERE season != 0 '
                'AND showid NOT IN (' + placeholder + ') '
                                                      'AND s.indexer_id = e.showid '
                                                      'AND airdate = (SELECT airdate '
                                                      'FROM tv_episodes inner_e '
                                                      'WHERE inner_e.season != 0 '
                                                      'AND inner_e.showid = e.showid '
                                                      'AND inner_e.airdate >= ? '
                                                      'ORDER BY inner_e.airdate ASC LIMIT 1) '
                                                      'AND e.status NOT IN (' + placeholder2 + ')',
                done_shows_list + [
                    next_week] + Quality.DOWNLOADED + Quality.SNATCHED + Quality.SNATCHED_BEST + Quality.SNATCHED_PROPER
        )

        results += db.select(
                'SELECT %s ' % fields_to_select +
                'FROM tv_episodes e, tv_shows s '
                'WHERE season != 0 '
                'AND s.indexer_id = e.showid '
                'AND airdate < ? '
                'AND airdate >= ? '
                'AND e.status IN (?,?) '
                'AND e.status NOT IN (' + ','.join(['?'] * len(qualities_list)) + ')',
                [today, recently, WANTED, UNAIRED] + qualities_list
        )

        results = [dict(result) for result in results]

        for index, item in enumerate(results):
            results[index][b'localtime'] = sbdatetime.convert_to_setting(
                    parse_date_time(item[b'airdate'], item[b'airs'], item[b'network']))

        results.sort(ComingEpisodes.sorts[sort])

        if not group:
            return results

        grouped_results = {category: [] for category in categories}

        for result in results:
            if result[b'paused'] and not paused:
                continue

            result[b'airs'] = str(result[b'airs']).replace('am', ' AM').replace('pm', ' PM').replace('  ', ' ')
            result[b'airdate'] = result[b'localtime'].toordinal()

            if result[b'airdate'] < today:
                category = 'missed'
            elif result[b'airdate'] >= next_week:
                category = 'later'
            elif result[b'airdate'] == today:
                category = 'today'
            else:
                category = 'soon'

            if len(categories) > 0 and category not in categories:
                continue

            if not result[b'network']:
                result[b'network'] = ''

            result[b'quality'] = get_quality_string(result[b'quality'])
            result[b'airs'] = sbdatetime.sbftime(result[b'localtime'], t_preset=timeFormat).lstrip('0').replace(' 0', ' ')
            result[b'weekday'] = 1 + date.fromordinal(result[b'airdate']).weekday()
            result[b'tvdbid'] = result[b'indexer_id']
            result[b'airdate'] = sbdatetime.sbfdate(result[b'localtime'], d_preset=dateFormat)
            result[b'localtime'] = result[b'localtime'].toordinal()

            grouped_results[category].append(result)

        return grouped_results
