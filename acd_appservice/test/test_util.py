import nest_asyncio
import pytest

nest_asyncio.apply()
from ..util import Util


@pytest.mark.asyncio
class TestUtil:
    async def test_is_email(self, util: Util):
        """`is_email` returns `True` if the given string is a valid email address,
        and `False` otherwise
        """
        assert util.is_email("foo@foo.com") == True
        assert util.is_email("foo_foo@foo.com") == True
        assert util.is_email("foo-foo@foo.com") == True
        assert util.is_email("foo123@foo.com") == True
        assert util.is_email("123foo@foo.com") == True
        assert util.is_email("Foo@foo.com") == False
        assert util.is_email(" foo@foo.com") == False
        assert util.is_email("foo@foo.com ") == False
        assert util.is_email(" foo@foo.com ") == False
        assert util.is_email("@foo:foo.com") == False
        assert util.is_email("!xyz:foo.com") == False
        assert util.is_email("#foo:foo.com") == False
        assert util.is_email("foo@foo@com") == False

    async def test_is_user_id(self, util: Util):
        """`is_user_id` checks if a string is a valid user ID"""
        assert util.is_user_id("@foo:foo.com") == True
        assert util.is_user_id("@foo_1:foo.com") == True
        assert util.is_user_id("@foo121:foo.com") == True
        assert util.is_user_id("@34443foo:foo.com") == True
        assert util.is_user_id("@Ahu7Ddfgvfoo:foo.com") == True
        assert util.is_user_id("@asf-frsa-foo:foo.com") == True
        assert util.is_user_id("@foo_foo:foo.com") == True
        assert util.is_user_id("foo@foo.com") == False
        assert util.is_user_id("!xyz:foo.com") == False
        assert util.is_user_id("#foo:foo.com") == False
        assert util.is_user_id("@foo@foo.com") == False

    async def test_is_room_id(self, util: Util):
        """It checks if a string is a valid room ID"""
        assert util.is_room_id("!xyz:foo.com") == True
        assert util.is_room_id("!asfgRgvre:foo.com") == True
        assert util.is_room_id("!1243grthtyij:foo.com") == True
        assert util.is_room_id("!Dasd_frer-ferfg:foo.com") == True
        assert util.is_room_id("!xyzFwe-gt--gsdf:foo.com") == True
        assert util.is_room_id("!xyz :foo.com") == False
        assert util.is_room_id("! xyz :foo.com") == False
        assert util.is_room_id("! xyz:foo.com") == False
        assert util.is_room_id("@foo:foo.com") == False
        assert util.is_room_id("foo@foo.com") == False
        assert util.is_room_id("#foo:foo.com") == False
        assert util.is_room_id("!xyz!foo.com") == False

    async def test_is_room_alias(self, util: Util):
        """`util.is_room_alias` returns `True` if the given string is a valid room alias,
        and `False` otherwise
        """
        assert util.is_room_alias("#foo:foo.com") == True
        assert util.is_room_alias("#asdj-gedgh-sdfg:foo.com") == True
        assert util.is_room_alias("#Erev_fdf-fdfs:foo.com") == True
        assert util.is_room_alias("#sd--arreth-:foo.com") == True
        assert util.is_room_alias("#foo :foo.com") == False
        assert util.is_room_alias("# foo :foo.com") == False
        assert util.is_room_alias("# foo:foo.com") == False
        assert util.is_room_alias("@foo:foo.com") == False
        assert util.is_room_alias("!xyz:foo.com") == False
        assert util.is_room_alias("foo@foo.com") == False
        assert util.is_room_alias("#fooo!foo.com") == False
