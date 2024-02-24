from __future__ import annotations

import datetime
import json
import time
from functools import wraps
from pathlib import Path
from typing import Callable, Iterator, NamedTuple, ParamSpec, TypeVar

import pandas as pd
import requests
from pydantic import AliasChoices, BaseModel, Field, computed_field
from tqdm import tqdm
from typing_extensions import Self

OptionalStr = None | str
T = TypeVar("T")
P = ParamSpec("P")

data_folder = Path("data")


def to_list(func: Callable[P, Iterator[T]]) -> Callable[P, list[T]]:
    """
    Decorator to convert a generator to a list
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs):
        return list(func(*args, **kwargs))

    return wrapper


class Month(NamedTuple):
    year: int
    month: int

    @classmethod
    def current_month(cls) -> Month:
        now = datetime.datetime.now()
        return cls(now.year, now.month)

    def next(self) -> Month:
        if self.month == 12:
            return Month(self.year + 1, 1)
        return Month(self.year, self.month + 1)

    def is_current(self) -> bool:
        return self == self.current_month()

    def is_future(self) -> bool:
        return self.months_to_current() < 0

    def months_to_current(self) -> int:
        current = self.current_month()
        return (current.year - self.year) * 12 + current.month - self.month

    @classmethod
    @to_list
    def all_months(cls) -> Iterator[Month]:
        month = Month(2016, 3)
        while not month.is_future():
            yield month
            month = month.next()


class RecordedMember(BaseModel):
    member_id: int = Field(validation_alias=AliasChoices("member_id", "MemberId"))
    name: str = Field(validation_alias=AliasChoices("name", "Name"))
    party: str = Field(validation_alias=AliasChoices("party", "Party"))
    sub_party: OptionalStr = Field(
        validation_alias=AliasChoices("sub_party", "SubParty")
    )
    party_colour: str = Field(
        validation_alias=AliasChoices("party_colour", "PartyColour")
    )
    party_abbreviation: OptionalStr = Field(
        validation_alias=AliasChoices("party_abbreviation", "PartyAbbreviation")
    )
    member_from: str = Field(validation_alias=AliasChoices("member_from", "MemberFrom"))
    list_as: OptionalStr = Field(validation_alias=AliasChoices("list_as", "ListAs"))
    proxy_name: OptionalStr = Field(
        validation_alias=AliasChoices("proxy_name", "ProxyName")
    )


class Division(BaseModel):
    division_id: int = Field(validation_alias=AliasChoices("division_id", "DivisionId"))
    date: str = Field(validation_alias=AliasChoices("date", "Date"))
    publication_updated: str = Field(
        validation_alias=AliasChoices("publication_updated", "PublicationUpdated")
    )
    number: int = Field(validation_alias=AliasChoices("number", "Number"))
    is_deferred: bool = Field(
        validation_alias=AliasChoices("is_deferred", "IsDeferred")
    )
    evel_type: OptionalStr = Field(
        validation_alias=AliasChoices("evel_type", "EVELType")
    )
    evel_country: OptionalStr = Field(
        validation_alias=AliasChoices("evel_country", "EVELCountry")
    )
    title: str = Field(validation_alias=AliasChoices("title", "Title"))
    aye_count: int = Field(validation_alias=AliasChoices("aye_count", "AyeCount"))
    no_count: int = Field(validation_alias=AliasChoices("no_count", "NoCount"))
    double_majority_aye_count: None | int = Field(
        validation_alias=AliasChoices(
            "double_majority_aye_count", "DoubleMajorityAyeCount"
        )
    )
    double_majority_no_count: None | int = Field(
        validation_alias=AliasChoices(
            "double_majority_no_count", "DoubleMajorityNoCount"
        )
    )
    friendly_description: OptionalStr = Field(
        validation_alias=AliasChoices("friendly_description", "FriendlyDescription")
    )
    friendly_title: OptionalStr = Field(
        validation_alias=AliasChoices("friendly_title", "FriendlyTitle")
    )
    remote_voting_start: OptionalStr = Field(
        validation_alias=AliasChoices("remote_voting_start", "RemoteVotingStart")
    )
    remote_voting_end: OptionalStr = Field(
        validation_alias=AliasChoices("remote_voting_end", "RemoteVotingEnd")
    )

    @computed_field
    def division_key(self) -> str:
        division_date = self.date.split("T")[0]
        return f"pw-{division_date}-{self.number}-commons"

    @computed_field
    def twfy_link(self) -> str:
        return f"https://www.theyworkforyou.com/divisions/{self.division_key}"

    @classmethod
    def get_month_divisions(
        cls, year: int, month: int, *, force_download: bool = False
    ) -> list[Self]:
        cached_file = data_folder / "raw" / "months" / f"{year}-{month:02d}.json"
        if cached_file.exists() and not force_download:
            data = json.loads(cached_file.read_text())
            return [cls.model_validate(d) for d in data]

        data = list(cls._get_month_divisions(year, month))
        cached_file.parent.mkdir(parents=True, exist_ok=True)
        cached_file.write_text(json.dumps([d.model_dump() for d in data], indent=2))
        return data

    @classmethod
    def _get_month_divisions(cls, year: int, month: int) -> Iterator[Self]:
        first_date_of_month = f"{year}-{month:02d}-01"
        if month == 12:
            first_date_of_next_month = f"{year+1}-01-01"
        else:
            first_date_of_next_month = f"{year}-{month+1:02d}-01"

        search_url = "https://commonsvotes-api.parliament.uk/data/divisions.json/search"
        retrieved_items = [None]
        skip_rate = 20
        skip = 0

        while retrieved_items:
            params = {
                "startDate": first_date_of_month,
                "endDate": first_date_of_next_month,
                "take": 20,
                "skip": skip,
            }
            time.sleep(5)
            response = requests.get(search_url, params=params)
            # print(response.content)
            retrieved_items = response.json()
            for d in retrieved_items:
                yield cls.model_validate(d)
            skip += skip_rate


class DivisionWithVotes(Division):
    aye_tellers: list[RecordedMember] | None = Field(
        validation_alias=AliasChoices("aye_tellers", "AyeTellers")
    )
    no_tellers: list[RecordedMember] | None = Field(
        validation_alias=AliasChoices("no_tellers", "NoTellers")
    )
    ayes: list[RecordedMember] = Field(validation_alias=AliasChoices("ayes", "Ayes"))
    noes: list[RecordedMember] = Field(validation_alias=AliasChoices("noes", "Noes"))
    no_vote_recorded: list[RecordedMember] = Field(
        validation_alias=AliasChoices("no_vote_recorded", "NoVoteRecorded")
    )

    @classmethod
    def get_from_id(cls, division_id: int) -> Self:
        url = f"https://commonsvotes-api.parliament.uk/data/division/{division_id}.json"
        response = requests.get(url)
        data = response.json()
        return cls.model_validate(data)


def get_all_months():
    for month in tqdm(Month.all_months()):
        Division.get_month_divisions(
            month.year, month.month, force_download=(month.months_to_current() < 3)
        )


def process_votes():
    divisions = []
    for month in Month.all_months():
        divisions.extend(Division.get_month_divisions(month.year, month.month))

    df = pd.DataFrame([d.model_dump() for d in divisions])

    df.to_parquet(
        data_folder / "packages" / "commons_votes" / "divisions.parquet",
        index=False,
    )
