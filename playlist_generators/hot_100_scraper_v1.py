import requests
from bs4 import BeautifulSoup
import spotipy
import spotipy.util as util
import os

def get_billboard_song_titles_for_year(year):
    """
    Scrapes Wikipedia  for billboard song titles for a given year, There might be better sources to parse from
    but i've chosen wikipeida for this first iteration because the page format is really standard, lightweight and
    hasn't changed for the last 18 years.
    :return: List of billboard songs and artists in a tuple '(song, artist)'
    """
    billboard_page = "https://en.wikipedia.org/wiki/Billboard_Year-End_Hot_100_singles_of_"
    page = requests.get(billboard_page + str(year))
    soup = BeautifulSoup(page.content, 'html.parser')
    doc = soup.find("table", {"class": "wikitable"})
    year_data = []
    for row in doc.find_all(["tr"])[1:]:
        # The th is required because ~2000+ uses that format instead
        row_data = [cell.text.strip() for cell in row.findAll(["td", "th"])]
        if len(row_data) != 3:
            print("Error Processing Row: ", row)
        else:
            year_data.append(tuple(row_data))
    return year_data

def parse_artist(content):
    for split_token in [" & ", " \\ ", " feat ", " featuring ", " and "]:
        content = content.partition(split_token)[0]
    return content

def parse_song(content):
    for split_token in ["\\", "/"]:
        content = content.partition(split_token)[0]
    return content

if __name__ == "__main__":
    """
    Prompts user for (login + year) and adds billboard hot 100 playlist for that given year to their profile. 
    """
    CLIENT_ID = "c6f00c6cca38465bbeaa7dd05f6f6b9c"
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    scope = 'user-library-read playlist-modify-public playlist-read-private playlist-modify-private'
    CACHE = '.spotipyoauthcache'

    username = input("Enter Your Spotify User Id: ")
    token = util.prompt_for_user_token(username, scope, client_id=CLIENT_ID,
                                       client_secret=CLIENT_SECRET,
                                       redirect_uri="http://localhost:8888")

    sp = spotipy.Spotify(auth=token)

    year = input("What year would you like to add to your profile?: ")
    if not ( year.isdigit() and int(year) > 1960 ):
        print("Error, You did not enter a valid year")
        exit(0)

    year_songs = get_billboard_song_titles_for_year(year)
    track_ids = []
    playlist = sp.user_playlist_create(username, "Billboard Hot 100 " + str(year), True)
    for (rank, track, artist) in year_songs:
        query = parse_artist(artist) + " " + parse_song(track)
        results = sp.search(q=query)
        try:
            track_ids.append(results['tracks']['items'][0]['uri'])
        except:
            print("Error! Could not find: ",(year, rank, track, query))
    sp.user_playlist_add_tracks(username, playlist['uri'], track_ids)
    print("Play List Complete!")