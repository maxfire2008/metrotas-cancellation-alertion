from pprint import pprint
import requests
import bs4
import datetime
import re

import sqlalchemy
import DatabaseController


database_controller = DatabaseController.DatabaseController("sqlite:///database.db")


def includes(a, b):
    if a is None:
        return True
    return a.lower() in b.lower()


def time_variations(time):
    """
    >>> time_variations("13:00")
    ['13:00', '1:00', '1300', '100']
    """

    time_split = time.split(":")
    try:
        hour = int(time_split[0])
        minute = int(time_split[1])

        return [
            time,
            time.replace(":", ""),
            f"{hour}:{minute:02}",
            f"{hour}:{minute:02}".replace(":", ""),
        ]
    except ValueError:
        return [time, time.replace(":", "")]


def process_article(date, title, url, description, location):
    print(f"scraper.py: {date} - {title} - {url} - {description} - {location}")
    if "Service Update" not in title:
        return

    article_content = requests.get(url, timeout=60)
    soup = bs4.BeautifulSoup(article_content.content, "html.parser")
    article = soup.find("article")

    lines = []

    for paragraph in article.findAll("p"):
        # replace \xa0+  with " "
        text = re.sub(r" +", " ", paragraph.text.replace("\xa0", " "))
        lines += text.split("\n")

    for text in lines:
        for alert in database_controller.get_alerts():
            if (
                includes("route", text)
                and includes(alert.route, text)
                and includes(alert.direction, text)
                and any(includes(t, text) for t in time_variations(alert.time))
            ):
                try:
                    database_controller.send_notification(
                        alert.user_id,
                        text,
                        f"{title} - {location} {date} {url}",
                        hash=repr((url, text)),
                    )
                    print("scraper.py: SENT NOTIFICATION FOR", alert)
                except sqlalchemy.exc.IntegrityError as error:
                    # check that "UNIQUE constraint failed: notifications.hash" is the error
                    if "UNIQUE constraint failed: notifications.hash" not in str(error):
                        raise error
                    else:
                        print("scraper.py: ALREADY SENT NOTIFICATION FOR", alert)


def main():
    alerts_index = requests.get("https://www.metrotas.com.au/alerts/", timeout=10)
    soup = bs4.BeautifulSoup(alerts_index.content, "html.parser")
    articles = soup.find("div", {"class": "article-body col-md-9"})
    for article in articles.findAll("article"):
        date = datetime.datetime.fromisoformat(article.find("time").attrs["datetime"])
        title = article.find("h4").text
        url = article.find("a").attrs["href"]
        description = article.find("p").text
        if description == "":
            description = None
        location = article.find("span").text

        process_article(date, title, url, description, location)


if __name__ == "__main__":
    main()
