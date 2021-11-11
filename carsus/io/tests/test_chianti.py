import pytest

from numpy.testing import assert_almost_equal
from carsus.io.chianti_ import ChiantiIonReader, ChiantiIngester
from carsus.model import Level, Ion, Line, ECollision


slow = pytest.mark.skipif(
    not pytest.config.getoption("--runslow"),
    reason="need --runslow option to run"
)


@pytest.fixture(scope="module")
def ch_ion_reader():
    return ChiantiIonReader("ne_2")


@pytest.fixture
def ch_ingester(memory_session):
    ions = 'ne 1; cl 3'
    ingester = ChiantiIngester(memory_session, ions=ions)
    return ingester


@pytest.mark.parametrize("ion_name", ["ne_2", "n_5"])
def test_chianti_bound_levels(ion_name):
    ion_rdr = ChiantiIonReader(ion_name)
    bound_levels = ion_rdr.bound_levels.reset_index()
    assert bound_levels["level_index"].max() <= ion_rdr.last_bound_level


@pytest.mark.parametrize("ion_name", ["ne_2", "n_5"])
def test_chianti_bound_lines(ion_name):
    ion_rdr = ChiantiIonReader(ion_name)
    bound_lines = ion_rdr.bound_lines.reset_index()
    assert bound_lines["upper_level_index"].max() <= ion_rdr.last_bound_level


@pytest.mark.parametrize("level_index, energy, energy_theoretical",[
    (1, 0, 0),
    (21, 252953.5, 252954),
])
def test_chianti_reader_read_levels(ch_ion_reader, level_index, energy, energy_theoretical):
    row = ch_ion_reader.levels.loc[level_index]
    assert_almost_equal(row['energy'], energy)
    assert_almost_equal(row['energy_theoretical'], energy_theoretical)


@slow
@pytest.mark.parametrize("atomic_number, ion_charge, levels_count",[
    (10, 1, 138),
    (17, 3, 5)
])
def test_chianti_ingest_levels_count(memory_session, ch_ingester, atomic_number, ion_charge, levels_count):
    ch_ingester.ingest(levels=True)
    ion = Ion.as_unique(memory_session, atomic_number=atomic_number, ion_charge=ion_charge)
    assert len(ion.levels) == levels_count


@slow
@pytest.mark.parametrize("atomic_number, ion_charge, lines_count",[
    (10, 1, 1999)
])
def test_chianti_ingest_lines_count(memory_session, ch_ingester, atomic_number, ion_charge, lines_count):
    ch_ingester.ingest(levels=True, lines=True)
    ion = Ion.as_unique(memory_session, atomic_number=atomic_number, ion_charge=ion_charge)
    cnt = memory_session.query(Line).join(Line.lower_level).filter(Level.ion==ion).count()
    assert cnt == lines_count


@slow
@pytest.mark.parametrize("atomic_number, ion_charge, e_col_count",[
    (10, 1, 9453)
])
def test_chianti_ingest_e_col_count(memory_session, ch_ingester, atomic_number, ion_charge, e_col_count):
    ch_ingester.ingest(levels=True, collisions=True)
    ion = Ion.as_unique(memory_session, atomic_number=atomic_number, ion_charge=ion_charge)
    cnt = memory_session.query(ECollision).join(ECollision.lower_level).filter(Level.ion==ion).count()
    assert cnt == e_col_count