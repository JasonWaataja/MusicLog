#!/usr/bin/env python3

import argparse
import datetime
import discogs_client
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET


def make_client():
    return discogs_client.Client(
        "Musiclog/0.0", user_token="JGcsRdInoDYHZleUNvDjZwhOeOQDRoEFhjdskVUu")


def find_text(tree, name, transform=None):
    """Returns the text of the first xml child named name in tree, transformed
    by transform.
    """
    child = tree.find(name)
    if child is not None:
        if transform:
            return transform(child.text)
        else:
            return child.text
    else:
        return None


def parse_date(date_string):
    """Returns a date object if valid iso8601, None otherwise."""
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", date_string)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        None


def sub_text(element, tag, text):
    """Returns a new sub-element of element with the given tag and text. Does
    nothing if text is None."""
    if text is None:
        return None
    else:
        element = ET.SubElement(element, tag)
        element.text = text
        return element


class Command():

    def make_parser(self):
        pass

    def execute(self, args):
        pass


class AlbumEntry():
    def __init__(self, album_id):
        self.album_id = album_id
        self.title = None
        self.artists = []
        self.rating = 0
        self.date = datetime.date.today()


class MusicLog():

    def __init__(self):
        self.albums = []

    def read(self, path):
        tree = ET.parse(path)
        root = tree.getroot()
        for child in root:
            album_id = int(child.get("id"))
            entry = AlbumEntry(album_id)
            entry.title = find_text(child, "title")
            for artist in child.findall("artist"):
                entry.artists.append(artist.text)
            entry.rating = find_text(child, "rating", lambda r: float(r))
            entry.date = find_text(child, "date", lambda d: parse_date(d))
            self.albums.append(entry)

    def write(self, path):
        root = ET.Element("musiclog")
        for album in self.albums:
            entry = ET.SubElement(root, "album")
            entry.attrib["id"] = str(album.album_id)
            sub_text(entry, "title", album.title)
            for artist in album.artists:
                sub_text(entry, "artist", artist)
            if album.rating:
                sub_text(entry, "rating", str(album.rating))
            sub_text(entry, "date", album.date.isoformat())
        tree = ET.ElementTree(root)
        tree.write(path)


ALBUM_RESULTS = 5
MUSICLOG_DIR = os.path.expanduser("~/.local/share/musiclog/")
MUSICLOG_NAME = "musiclog.xml"


def musiclog_path():
    return os.path.join(MUSICLOG_DIR, MUSICLOG_NAME)


def print_album_results(results):
    """Returns the count of albums printed."""
    count = min(len(results), ALBUM_RESULTS)
    for i in range(count):
        print("{}: {}".format(i + 1, results[i].title))
    return count


def get_album_index(count):
    """Returns a number in [0-ALBUM_RESULTS) or None"""
    while True:
        index = input(
            "Enter a number 1-{} (empty for default): ".format(count))
        if index:
            try:
                index = int(index)
                if index >= 1 and index <= ALBUM_RESULTS:
                    return index - 1
                else:
                    print("Please enter a valid index.")
            except ValueError:
                print("Please enter a number.")
        else:
            return 0


def add_album_interactive(log, results, args):
    count = print_album_results(results)
    index = get_album_index(count)
    if index:
        rating = input("Enter a rating (empty for none): ")
        if rating:
            try:
                rating = float(rating)
            except ValueError:
                rating = None
        else:
            rating = None
        album = results[index]
        entry = AlbumEntry(album.id)
        entry.title = album.title
        entry.artists = [artist.name for artist in album.artists]
        entry.rating = rating
        log.albums.append(entry)


def add_album(log, results, args):
    album = results[0]
    entry = AlbumEntry(album.id)
    entry.title = album.title
    entry.artists = [artist.name for artist in album.artists]
    if args.rating:
        entry.rating = float(args.rating)
    log.albums.append(entry)


class AddCommand(Command):

    def make_parser(self):
        parser = argparse.ArgumentParser(description="Add an album")
        parser.add_argument("name")
        parser.add_argument("-r", "--rating", help="Rate the albukm")
        parser.add_argument("-i", "--interactive", action="store_true",
                            help="Prompt for information")
        return parser

    def execute(self, args):
        client = make_client()
        log = MusicLog()
        try:
            log.read(musiclog_path())
        except FileNotFoundError:
            pass
        results = client.search(args.name, type="release")
        if not results:
            print("No results for {}".format(args.name))
            return
        if args.interactive:
            add_album_interactive(log, results, args)
        else:
            add_album(log, results, args)
        pathlib.Path(MUSICLOG_DIR).mkdir(parents=True, exist_ok=True)
        log.write(musiclog_path())


def album_has_artist(album, artist_re):
    for artist in album.artists:
        if re.search(artist_re, artist):
            return True
    return False


class SearchCommand(Command):

    def make_parser(self):
        parser = argparse.ArgumentParser(description="Search logged albums")
        parser.add_argument("-t", "--title", help="Title of album")
        parser.add_argument("-a", "--artist", help="Album of album")
        parser.add_argument("-r", "--rating", help="Exact rating of album")
        parser.add_argument("-m", "--min", help="Minimum rating")
        parser.add_argument("-M", "--max", help="Maximum rating")
        return parser

    def execute(self, args):
        log = MusicLog()
        log.read(musiclog_path())
        albums = log.albums
        if args.title:
            albums = filter(lambda a: re.search(args.title, a.title), albums)
        if args.artist:
            albums = filter(lambda a: album_has_artist(a, args.artist), albums)
        if args.rating:
            albums = filter(lambda a: a.rating == float(args.rating), albums)
        if args.min:
            albums = filter(lambda a: a.rating >= float(args.min), albums)
        if args.max:
            albums = filter(lambda a: a.rating <= float(args.max), albums)
        for album in albums:
            print(album.title)


def make_parser():
    parser = argparse.ArgumentParser(
        description="Log the music you listen to.")
    parser.add_argument("command", help="Action to take")
    return parser


def make_commands():
    commands = {}
    commands["add"] = AddCommand()
    commands["a"] = commands["add"]
    commands["search"] = SearchCommand()
    commands["s"] = commands["search"]
    return commands


def main(argv):
    parser = make_parser()
    args = parser.parse_args(argv[1:2])
    commands = make_commands()
    cmd = args.command
    if cmd and cmd in commands:
        command = commands[cmd]
        parser = command.make_parser()
        args = parser.parse_args(argv[2:])
        commands[cmd].execute(args)
    else:
        print("Unknown command {}".format(cmd))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
