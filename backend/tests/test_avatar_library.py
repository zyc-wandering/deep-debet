import json

from app.avatars.library import (
    ALLOWED_ETHNICITIES,
    ALLOWED_GENDERS,
    ALLOWED_SKIN_TONES,
    AvatarLibrary,
)
from app.models import DebaterConfig


def write_manifest(tmp_path, assets):
    images = tmp_path / "images"
    images.mkdir()
    for asset in assets:
        (images / asset["src"].removeprefix("avatar-library/")).write_bytes(b"png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(assets), encoding="utf-8")
    return manifest


def test_avatar_library_loads_manifest_and_matches_metadata(tmp_path):
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "east_female",
                "src": "avatar-library/east_female.png",
                "name": "East Female",
                "ethnicity": "east_asian",
                "skin_tone": "light",
                "gender": "female",
                "tags": ["policy"],
            },
            {
                "id": "south_male",
                "src": "avatar-library/south_male.png",
                "name": "South Male",
                "ethnicity": "south_asian",
                "skin_tone": "tan",
                "gender": "male",
                "tags": ["finance"],
            },
        ],
    )
    library = AvatarLibrary(manifest)

    debater = DebaterConfig(
        name="Zhang Min",
        gender="female",
        ethnicity="Chinese",
        background="Government policy researcher",
        stance="Supports strict regulation",
        personality="measured",
    )

    chosen = library.choose(debater, session_id="session-1")

    assert chosen is not None
    assert chosen.id == "east_female"
    assert library.resolve_path(chosen.src).name == "east_female.png"


def test_avatar_library_assigns_unique_avatars_until_pool_exhausted(tmp_path):
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "a1",
                "src": "avatar-library/a1.png",
                "name": "A1",
                "ethnicity": "east_asian",
                "skin_tone": "light",
                "gender": "male",
                "tags": [],
            },
            {
                "id": "a2",
                "src": "avatar-library/a2.png",
                "name": "A2",
                "ethnicity": "east_asian",
                "skin_tone": "light",
                "gender": "male",
                "tags": [],
            },
            {
                "id": "a3",
                "src": "avatar-library/a3.png",
                "name": "A3",
                "ethnicity": "east_asian",
                "skin_tone": "light",
                "gender": "male",
                "tags": [],
            },
        ],
    )
    library = AvatarLibrary(manifest)
    debaters = [
        DebaterConfig(
            name=f"Debater {index}",
            gender="male",
            ethnicity="Chinese",
            background="Policy analyst",
            stance="stance",
            personality="direct",
        )
        for index in range(3)
    ]

    avatars = library.assign_to_debaters(debaters, "session-unique")

    assert len(avatars) == 3
    assert len({debater.avatar_id for debater in debaters}) == 3
    assert all(debater.avatar_url.startswith("avatar-library/") for debater in debaters)


def test_avatar_library_restricts_by_identity_before_tag_scoring(tmp_path):
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "east_male",
                "src": "avatar-library/east_male.png",
                "name": "East Male",
                "ethnicity": "east_asian",
                "skin_tone": "light",
                "gender": "male",
                "tags": ["policy"],
            },
            {
                "id": "south_male_finance",
                "src": "avatar-library/south_male_finance.png",
                "name": "South Male Finance",
                "ethnicity": "south_asian",
                "skin_tone": "tan",
                "gender": "male",
                "tags": ["finance", "market", "operator"],
            },
        ],
    )
    library = AvatarLibrary(manifest)
    debater = DebaterConfig(
        name="Chen Wei",
        gender="male",
        ethnicity="Chinese",
        background="Finance market operator",
        stance="stance",
        personality="direct",
    )

    chosen = library.choose(debater, session_id="session-identity")

    assert chosen is not None
    assert chosen.id == "east_male"


def test_avatar_library_respects_gender_before_ethnicity_when_no_exact_pool(tmp_path):
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "east_male",
                "src": "avatar-library/east_male.png",
                "name": "East Male",
                "ethnicity": "east_asian",
                "skin_tone": "light",
                "gender": "male",
                "tags": ["policy"],
            },
            {
                "id": "white_female",
                "src": "avatar-library/white_female.png",
                "name": "White Female",
                "ethnicity": "white_european",
                "skin_tone": "light",
                "gender": "female",
                "tags": ["finance"],
            },
        ],
    )
    library = AvatarLibrary(manifest)
    debater = DebaterConfig(
        name="Zhang Min",
        gender="female",
        ethnicity="Chinese",
        background="Finance analyst",
        stance="stance",
        personality="direct",
    )

    chosen = library.choose(debater, session_id="session-gender")

    assert chosen is not None
    assert chosen.id == "white_female"


def test_checked_in_avatar_manifest_metadata_is_consistent():
    library = AvatarLibrary()

    assert len(library.assets) == 32
    ids = [asset.id for asset in library.assets]
    srcs = [asset.src for asset in library.assets]
    assert len(ids) == len(set(ids))
    assert len(srcs) == len(set(srcs))

    for asset in library.assets:
        assert asset.ethnicity in ALLOWED_ETHNICITIES
        assert asset.skin_tone in ALLOWED_SKIN_TONES
        assert asset.gender in ALLOWED_GENDERS
        assert asset.src == f"avatar-library/{asset.id}.png"
        assert asset.id.startswith(f"{asset.ethnicity}_{asset.gender}_")
        assert library.resolve_path(asset.src) is not None

    covered_ethnicities = {asset.ethnicity for asset in library.assets}
    assert ALLOWED_ETHNICITIES.issubset(covered_ethnicities)
    assert {"male", "female"}.issubset({asset.gender for asset in library.assets})
