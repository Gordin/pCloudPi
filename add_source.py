#!/usr/bin/env python3
import sqlite3
import xml.etree.ElementTree as ET
from functools import reduce
import logging
import configparser

class KodiPath(object):
    KEYS = '("strPath", "strContent", "strScraper", "strHash", "scanRecursive", "useFolderNames", "strSettings", "noUpdate", "exclude", "dateAdded", "idParentPath")'
    CONTENT_SCRAPER_MAPPING = {
        'tvshows': 'metadata.tvshows.themoviedb.org',
        'movies': 'metadata.themoviedb.org'
    }
    CONTENT_SETTINGS_MAPPING = {
        'tvshows': '<settings version="2"><setting id="alsoimdb" default="true">false</setting><setting id="certprefix" default="true"></setting><setting id="fallback">true</setting><setting id="fanarttvart">true</setting><setting id="keeporiginaltitle" default="true">false</setting><setting id="language" default="true">en</setting><setting id="RatingS" default="true">Themoviedb</setting><setting id="tmdbart">true</setting><setting id="tmdbcertcountry" default="true">us</setting><setting id="tvdbwidebanners">true</setting></settings>',
        'movies': '<settings version="2"><setting id="certprefix" default="true">Rated </setting><setting id="fanart">true</setting><setting id="imdbanyway" default="true">false</setting><setting id="keeporiginaltitle" default="true">false</setting><setting id="language" default="true">en</setting><setting id="RatingS" default="true">TMDb</setting><setting id="tmdbcertcountry" default="true">us</setting><setting id="trailer">true</setting></settings>'
    }

    @staticmethod
    def from_config(config_file):
        config = configparser.ConfigParser()
        config.read(config_file)
        conf = config['config']
        logging.debug(config.sections())
        logging.debug(config['config'])
        name = conf['source_name']
        path = 'http://127.0.0.1:{}/'.format(conf['pcloud_port'])
        content = conf['source_content']
        return KodiPath(name, path, content)

    def __init__(self, name, path, content):
        self.name = name
        self.path = path
        self.content = content

    def insert_string(self, ):
        return ''' INSERT INTO "main"."path" {} VALUES ('{}', '{}', '{}', '', '1', '0', '{}', '0', '0', '', '');
        '''.format(
            str(KodiPath.KEYS),
            self.path,
            self.content,
            self._scraper_for_content_type(self.content),
            self._settings_for_content_type(self.content),
        )

    def add_to_database(self, path):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cmd = self.insert_string()
        cursor.execute(cmd)
        conn.commit()
        cursor.close()

    def __create_default_sources_xml(self, xml_path):
        sources = ET.Element('sources')
        programs = ET.SubElement(sources, 'programs')
        video = ET.SubElement(sources, 'video')
        music = ET.SubElement(sources, 'music')
        pictures = ET.SubElement(sources, 'pictures')
        files = ET.SubElement(sources, 'files')
        games = ET.SubElement(sources, 'games')
        for source in sources:
            default = ET.SubElement(source, 'default')
            default.set("pathversion", "1")
        return ET.ElementTree(sources)

    def __create_default_mediasources_xml(self, xml_path):
        mediasources = ET.Element('mediasources')
        network = ET.SubElement(mediasources, 'network')
        return ET.ElementTree(mediasources)

    def add_to_sources(self, xml_path):
        try:
            logging.debug("Trying to open sources.xml at {}".format(xml_path))
            tree = ET.parse(xml_path)
        except FileNotFoundError:
            logging.info("Didn't find sources.xml, creating default file...")
            tree = self.__create_default_sources_xml(xml_path)
        video = tree.getroot().find('video')
        if len([x for x in video.findall('source') if x.find('path').text == self.path]):
            return
        source = ET.SubElement(video, 'source')
        name = ET.SubElement(source, 'name')
        name.text = self.name
        path = ET.SubElement(source, 'path')
        path.set("pathversion", "1")
        path.text = self.path
        allowsharing = ET.SubElement(source, 'allowsharing')
        allowsharing.text = "true"
        logging.debug("writing sources.xml to {}".format(xml_path))
        tree.write(xml_path)

    def add_to_mediasources(self, xml_path):
        try:
            logging.debug("Trying to open mediasources.xml at {}".format(xml_path))
            tree = ET.parse(xml_path)
        except FileNotFoundError:
            logging.info("Didn't find mediasources.xml, creating default file...")
            tree = self.__create_default_mediasources_xml(xml_path)
        xml_root = tree.getroot()
        network = xml_root.find('network')
        if network is None:
            network = ET.SubElement(xml_root, 'network')
        if len([x for x in network.findall('location') if x.text == self.path]):
            return
        location = ET.SubElement(network, 'location')
        location.text = self.path
        location.set('id', self.__next_media_source_id(network))
        tree.write(xml_path)

    def __next_media_source_id(self, network_node):
        highest_id = max(int(l.get('id', default=-2)) for l in network_node.findall('location'))
        return str(highest_id + 1)

    def add_to_kodi(self, kodi_config_dir):
        # The 116 is the version of the schema. See https://kodi.wiki/view/Databases#Database_Versions
        # Right now Kodi v18 and v19 are using 116
        self.add_to_database(kodi_config_dir + 'userdata/Database/MyVideos116.db')
        self.add_to_mediasources(kodi_config_dir + 'userdata/mediasources.xml')
        self.add_to_sources(kodi_config_dir + 'userdata/sources.xml')

    def _scraper_for_content_type(self, content):
        return KodiPath.CONTENT_SCRAPER_MAPPING[content]

    def _settings_for_content_type(self, content):
        return KodiPath.CONTENT_SETTINGS_MAPPING[content]

class KodiSourceManager(object):
    def connect(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def load_sources_xml(self):
        tree = ET.parse(self.sources_xml_path)
        return tree, tree.getroot()

    def clear_video_sources(self):
        try:
            tree, xml_root = self.load_sources_xml()
        except FileNotFoundError:
            return
        video = xml_root.find('video')
        video_sources = video.findall('source')
        for source in video_sources:
            video.remove(source)
        tree.write(self.sources_xml_path)

    def disconnect(self):
        self.cursor.close()

    def __init__(self, kodi_config_dir='/home/pi/.kodi/'):
        self.kodi_config_dir = kodi_config_dir
        self.path = self.kodi_config_dir + 'userdata/Database/MyVideos116.db'
        self.sources_xml_path = self.kodi_config_dir + 'userdata/sources.xml'
        self.mediasources_xml_path = self.kodi_config_dir + 'userdata/mediasources.xml'
        logging.basicConfig(level=logging.DEBUG)

    def get_sources(self):
        self.connect()
        self.cursor.execute('select * from path where strContent NOT NULL')
        sources = self.cursor.fetchall()
        self.disconnect()
        return sources

    def drop_sources(self):
        logging.debug("Sources before: {}".format(len(self.get_sources())))
        self.connect()
        self.cursor.execute('DELETE FROM path where strContent NOT NULL')
        self.conn.commit()
        self.disconnect()
        logging.debug("Sources after: {}".format(len(self.get_sources())))

    def insert_source_from_kodipath(self, kodipath):
        self.connect()
        kodipath.add_to_kodi(self.kodi_config_dir)
        self.disconnect()

    def insert_source(self, name, path, content):
        path_obj = KodiPath(name, path, content)
        self.insert_source_from_kodipath(path_obj)

    def test_insert(self):
        self.drop_sources()
        self.clear_video_sources()
        self.insert_source('Serien', 'http://127.0.0.1:13531/', 'tvshows')

def add_source(args):
    m = KodiSourceManager()
    m.insert_source(args.name, args.path, args.type)

def clear_sources(args):
    m = KodiSourceManager()
    m.drop_sources()
    m.clear_video_sources()

def test_config_read(args):
    KodiPath.from_config(args.config)

def add_from_config(args):
    m = KodiSourceManager()
    kodipath = KodiPath.from_config(args.config)
    m.insert_source_from_kodipath(kodipath)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Add some integers.')
    subparsers = parser.add_subparsers(help='sub-command help')

    parser_add = subparsers.add_parser('add', help='Add a source')
    parser_add.add_argument('name', help='Name of the source')
    parser_add.add_argument('path', help='Path to the source')
    parser_add.add_argument('type', choices=['tvshows', 'movies'], help='type of the source')
    parser_add.set_defaults(func=add_source)

    parser_clear = subparsers.add_parser('clear', help='Removes all sources')
    parser_clear.set_defaults(func=clear_sources)

    parser_test = subparsers.add_parser('test_config_read', help='Removes all sources')
    parser_test.add_argument('config', help='Path to config file')
    parser_test.set_defaults(func=test_config_read)

    parser_test = subparsers.add_parser('add_from_config', help='adds source from config file')
    parser_test.add_argument('config', help='Path to config file')
    parser_test.set_defaults(func=add_from_config)

    args = parser.parse_args()
    args.func(args)
