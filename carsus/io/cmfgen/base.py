import logging
import pathlib

import astropy.units as u
import numpy as np
import pandas as pd
import roman
import yaml

from carsus import __path__ as CARSUS_PATH
from carsus.io.base import BaseParser
from carsus.util import convert_atomic_number2symbol, parse_selected_species

from .util import *

logger = logging.getLogger(__name__)


class CMFGENEnergyLevelsParser(BaseParser):
    """
    Description
    ----------
    base : pandas.DataFrame
    columns : list of str
    meta : dict
        Metadata extracted from file header.

    Methods
    -------
    load(fname)
        Parses the input file and stores the result in the `base` attribute.
    """

    keys = ['!Date',
            '!Format date',
            '!Number of energy levels',
            '!Ionization energy',
            '!Screened nuclear charge',
            '!Number of transitions',
            ]

    def load(self, fname):
        meta = parse_header(fname, self.keys)
        skiprows, _ = find_row(fname, "Number of transitions")
        nrows = int(meta['Number of energy levels'])
        config = {'header': None,
                  'index_col': False,
                  'sep': '\s+',
                  'skiprows': skiprows,
                  'nrows': nrows,
                  'engine': 'python',
                  }

        try:
            df = pd.read_csv(fname, **config)

        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=columns)
            logger.warning(f'Empty table: `{fname}`.')

        if df.shape[1] == 10:
            # Read column names and split them keeping just one space (e.g. '10^15 Hz')
            _, columns = find_row(fname, 'E(cm^-1)', "Lam")
            columns = columns.split('  ')
            columns = [c.rstrip().lstrip() for c in columns if c != '']
            columns = ['label'] + columns
            df.columns = columns

        elif df.shape[1] == 7:
            df.columns = ['label', 'g', 'E(cm^-1)', 'eV', 'Hz 10^15', 'Lam(A)', 'ID']

        elif df.shape[1] == 6:
            df.columns = ['label', 'g', 'E(cm^-1)', 'Hz 10^15', 'Lam(A)', 'ID']

        elif df.shape[1] == 5:
            df.columns = ['label', 'g', 'E(cm^-1)', 'eV', 'ID']

        else:
            logger.warning(f'Unknown column format: `{fname}`.')

        self.base = df
        self.columns = df.columns.tolist()
        self.fname = fname
        self.meta = meta

    def to_hdf(self, key='/energy_levels'):
        if not self.base.empty:
            with pd.HDFStore('{}.h5'.format(self.fname), 'w') as f:
                f.put(key, self.base)
                f.get_storer(key).attrs.metadata = self.meta


class CMFGENOscillatorStrengthsParser(BaseParser):
    """
        Description
        ----------
        base : pandas.DataFrame
        columns : list of str
        meta : dict
            Metadata extracted from file header.

        Methods
        -------
        load(fname)
            Parses the input file and stores the result in the `base` attribute.
    """

    keys = CMFGENEnergyLevelsParser.keys

    def load(self, fname):
        meta = parse_header(fname, self.keys)
        skiprows, _ = find_row(fname, "Transition", "Lam")
        skiprows += 1

        # Parse only tables listed increasing lower level i, e.g. `FE/II/24may96/osc_nahar.dat`
        nrows = int(meta['Number of transitions'])
        config = {'header': None,
                  'index_col': False,
                  'sep': '\s*\|\s*|-?\s+-?\s*|(?<=[^ED\s])-(?=[^\s])',
                  'skiprows': skiprows,
                  'nrows': nrows,
                  'engine': 'python',
                  }

        columns = ['label_lower', 'label_upper', 'f', 'A',
                    'Lam(A)', 'i', 'j', 'Lam(obs)', '% Acc']

        try:
            df = pd.read_csv(fname, **config)

        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=columns)
            logger.warning(f'Empty table: `{fname}`.')

        if df.shape[1] == 9:
            df.columns = columns

        # These files have 9-column, but the current regex produces 10 columns
        elif df.shape[1] == 10:
            df.columns = columns + ['?']
            df = df.drop(columns=['?'])

        elif df.shape[1] == 8:
            df.columns = columns[:7] + ['#']
            df = df.drop(columns=['#'])
            df['Lam(obs)'] = np.nan
            df['% Acc'] = np.nan

        else:
            logger.warning(f'Unknown column format: `{fname}`.')

        if df.shape[0] > 0 and 'D' in str(df['f'][0]):
            df['f'] = df['f'].map(to_float)
            df['A'] = df['A'].map(to_float)

        self.base = df
        self.columns = df.columns.tolist()
        self.fname = fname
        self.meta = meta

    def to_hdf(self, key='/oscillator_strengths'):
        if not self.base.empty:
            with pd.HDFStore('{}.h5'.format(self.fname), 'w') as f:
                f.put(key, self.base)
                f.get_storer(key).attrs.metadata = self.meta


class CMFGENCollisionalStrengthsParser(BaseParser):
    """
        Description
        ----------
        base : pandas.DataFrame
        columns : list of str
        meta : dict
            Metadata extracted from file header.

        Methods
        -------
        load(fname)
            Parses the input file and stores the result in the `base` attribute.
    """

    keys = ['!Number of transitions',
            '!Number of T values OMEGA tabulated at',
            '!Scaling factor for OMEGA (non-FILE values)',
            '!Value for OMEGA if f=0',
            ]

    def load(self, fname):
        meta = parse_header(fname, self.keys)
        skiprows, _ = find_row(fname, "ransition\T")
        config = {'header': None,
                  'index_col': False,
                  'sep': '\s*-?\s+-?|(?<=[^edED])-|(?<=[FDP]e)-',
                  'skiprows': skiprows,
                  'engine': 'python',
                  }

        # FIXME: expensive solution for two files containing more than one 
        # table: `ARG/III/19nov07/col_ariii` & `HE/II/5dec96/he2col.dat`
        end, _ = find_row(fname, "Johnson values:", "dln_OMEGA_dlnT", how='OR')

        if end is not None:
            config['nrows'] = end - config['skiprows'] -2

        try:
            _, columns = find_row(fname, 'ransition\T')
            columns = columns.split()
            
            # NOTE: Comment next line when trying new regexes
            columns = [np.format_float_scientific(
                to_float(x)*1e+04, precision=4) for x in columns[1:]]
            config['names'] = ['label_lower', 'label_upper'] + columns

        # FIXME: some files have no column names nor header
        except AttributeError:
            logger.warning(f'Unknown column format: `{fname}`.')

        try:
            df = pd.read_csv(fname, **config)
            for c in df.columns[2:]:  # This is done column-wise on purpose
                try:
                    df[c] = df[c].astype('float64')

                except ValueError:
                    df[c] = df[c].map(to_float).astype('float64')

        except pd.errors.EmptyDataError:
            df = pd.DataFrame()
            logger.warning(f'Empty table: `{fname}`.')

        self.base = df
        self.columns = df.columns.tolist()
        self.fname = fname
        self.meta = meta

    def to_hdf(self, key='/collisional_strengths'):
        if not self.base.empty:
            with pd.HDFStore('{}.h5'.format(self.fname), 'w') as f:
                f.put(key, self.base)
                f.get_storer(key).attrs.metadata = self.meta


class CMFGENPhotoionizationCrossSectionParser(BaseParser):
    """
        Description
        ----------
        base : list of pandas.DataFrame
        columns : list of str
        meta : dict
            Metadata extracted from file header.

        Methods
        -------
        load(fname)
            Parses the input file and stores the result in the `base` attribute.
    """

    keys = ['!Date',
            '!Number of energy levels',
            '!Number of photoionization routes',
            '!Screened nuclear charge',
            '!Final state in ion',
            '!Excitation energy of final state',
            '!Statistical weight of ion',
            '!Cross-section unit',
            '!Split J levels',
            '!Total number of data pairs',
            ]

    def _table_gen(self, f):
        """Yields a cross section table for a single energy level target.

        Parameters
        ----------
        f : file buffer

        Yields
        -------
        pd.DataFrame
            DataFrame with attached metadata.
        """
        data = []
        meta = {}

        for line in f:
            
            try:
                value = line.split()[0]

            except IndexError:
                continue

            if '!Configuration name' in line:
                meta['Configuration name'] = value

            if '!Type of cross-section' in line:
                meta['Type of cross-section'] = int(value)

            if '!Number of cross-section points' in line:
                n_points = int(value)
                for i in range(n_points):

                    values = f.readline().split()
                    if len(values) == 8:  # Verner & Yakolev (1995) ground state fits

                        data.append(
                            list(map(int, values[:2])) + list(map(to_float, values[2:])))

                        if i == n_points/len(values) -1:
                            break

                    else:
                        data.append(map(to_float, values))

                meta['Number of cross-section points'] = n_points
                break

        arr = np.array(data)
        yield arr, meta

    def load(self, fname):

        data = []
        column_types = set()
        meta = parse_header(fname, self.keys)

        with open_cmfgen_file(fname) as f:

            while True:

                arr, meta_ = next(self._table_gen(f), None)
                df = pd.DataFrame.from_records(arr)
                df.attrs = meta_

                if df.empty:
                    break
                
                elif df.shape[1] == 2:
                    columns = ['energy', 'sigma']

                elif df.shape[1] == 1:
                    columns = ['fit_coeff']

                elif df.shape[1] == 8:  # Verner & Yakolev (1995) ground state fits
                    columns = ['n', 'l', 'E', 'E_0', 'sigma_0', 'y(a)', 'P', 'y(w)']

                else:
                    logger.warning(f'Unknown column format: `{fname}`.')

                column_types.add(tuple(columns))
                df.columns = columns
                data.append(df)

        self.base = data
        self.columns = sorted(column_types)
        self.fname = fname
        self.meta = meta

    def to_hdf(self, key='/photoionization_cross_sections'):
        if len(self.base) > 0:
            with pd.HDFStore('{}.h5'.format(self.fname), 'w') as f:

                for i in range(0, len(self.base)-1):
                    subkey = '{0}/{1}'.format(key, i)
                    f.put(subkey, self.base[i])
                    f.get_storer(subkey).attrs.metadata = self.base[i].attrs

                f.root._v_attrs['metadata'] = self.meta


class CMFGENHydLParser(BaseParser):
    """
    Parser for the CMFGEN hydrogen photoionization cross sections.

    Attributes
    ----------
    base : pandas.DataFrame, dtype float
        Photoionization cross section table for hydrogen. Values are the
        common logarithm (i.e. base 10) of the cross section in units cm^2.
        Indexed by the principal quantum number n and orbital quantum
        number l.
    columns : list of float
        The frequencies for the cross sections. Given in units of the threshold
        frequency for photoionization.
    meta : dict
        Metadata extracted from file header.

    Methods
    -------
    load(fname)
        Parses the input file and stores the result in the `base` attribute.
    """

    keys = [
        '!Maximum principal quantum number',
        '!Number of values per cross-section',
        '!L_ST_U',
        '!L_DEL_U'
    ]
    nu_ratio_key = 'L_DEL_U'

    def load(self, fname):
        meta = parse_header(fname, self.keys)
        self.meta = meta
        self.max_l = self.get_max_l()

        self.num_xsect_nus = int(meta['Number of values per cross-section'])
        nu_ratio = 10**float(meta[self.nu_ratio_key])
        nus = np.power(
            nu_ratio,
            np.arange(self.num_xsect_nus)
        )  # in units of the threshold frequency

        skiprows, _ = find_row(fname, self.nu_ratio_key)
        skiprows += 1

        data = []
        indexes = []
        with open(fname, mode='r') as f:
            for i in range(skiprows):
                f.readline()
            while True:
                n, l, log10x_sect = next(self._table_gen(f), None)
                indexes.append((n, l))
                data.append(log10x_sect)
                if l == self.max_l:
                    break

        index = pd.MultiIndex.from_tuples(indexes, names=['n', 'l'])
        self.base = pd.DataFrame(data, index=index, columns=nus)
        self.base.columns.name = 'nu / nu_0'

        # self.base -= 10.  # Convert from cmfgen units to log10(cm^2)
        self.columns = self.base.columns.tolist()
        self.fname = fname

    def _table_gen(self, f):
        """Yields a logarithmic cross section table for a hydrogen level.

        Parameters
        ----------
        f : file buffer

        Yields
        -------
        int
            Principal quantum number n.
        int
            Principal quantum number l.
        numpy.ndarray, dtype float
            Photoionization cross section table. Values are the common
            logarithm (i.e. base 10) of the cross section in units cm^2.
        """
        line = f.readline()
        n, l, num_entries = self.parse_table_header_line(line)
        assert(num_entries == self.num_xsect_nus)

        log10_xsect = []
        while True:
            line = f.readline()
            if not line.strip():  # This is the end of the current table
                break
            log10_xsect += [float(entry) for entry in line.split()]

        log10_xsect = np.array(log10_xsect)
        assert(len(log10_xsect) == self.num_xsect_nus)

        yield n, l, log10_xsect

    @staticmethod
    def parse_table_header_line(line):
        return [int(entry) for entry in line.split()]

    def get_max_l(self):
        return int(self.meta['Maximum principal quantum number']) - 1

    def to_hdf(self, key='/hyd_l_data'):
        if not self.base.empty:
            with pd.HDFStore('{}.h5'.format(self.fname), 'w') as f:
                f.put(key, self.base)
                f.get_storer(key).attrs.metadata = self.meta


class CMFGENHydGauntBfParser(CMFGENHydLParser):
    """
    Parser for the CMFGEN hydrogen bound-free gaunt factors.

    Attributes
    ----------
    base : pandas.DataFrame, dtype float
        Bound-free gaunt factors for hydrogen.
        Indexed by the principal quantum number n.
    columns : list of float
        The frequencies for the gaunt factors. Given in units of the threshold
        frequency for photoionization.
    meta : dict
        Metadata extracted from file header.

    Methods
    -------
    load(fname)
        Parses the input file and stores the result in the `base` attribute.
    """

    keys = [
        "!Maximum principal quantum number",
        "!Number of values per cross-section",
        "!N_ST_U",
        "!N_DEL_U",
    ]
    nu_ratio_key = "N_DEL_U"

    @staticmethod
    def parse_table_header_line(line):
        line_split = [int(entry) for entry in line.split()]
        n, l, num_entries = (
            line_split[0],
            line_split[0],
            line_split[1],
        )  # use n as mock l value
        return n, l, num_entries

    def load(self, fname):
        super().load(fname)
        self.base.index = self.base.index.droplevel("l")
        # self.base += 10.0  # undo unit conversion used in CMFGENHydLParser

    def get_max_l(self):
        return int(self.meta["Maximum principal quantum number"])

    def to_hdf(self, key="/gbf_n_data"):
        super().to_hdf(key)


class CMFGENReader:
    """
    Class for extracting levels and lines from CMFGEN.
    
    Mimics the GFALLReader class.

    Attributes
    ----------
    levels : DataFrame
    lines : DataFrame

    """

    def __init__(self, data, priority=10):
        """
        Parameters
        ----------
        data : dict
            Dictionary containing one dictionary per species with 
            keys `levels` and `lines`.

        priority: int, optional
            Priority of the current data source, by default 10.
        """
        self.priority = priority
        self.ions = list(data.keys())
        self._get_levels_lines(data)

    @classmethod
    def from_config(cls, ions, atomic_path, priority=10, cross_sections=False, config_yaml=None):

        ATOMIC_PATH = pathlib.Path(atomic_path)
        if config_yaml is not None:
            YAML_PATH = pathlib.Path(config_yaml).as_posix()

        else:
            YAML_PATH = pathlib.Path(CARSUS_PATH[0]).joinpath('data', 'config.yml').as_posix()
            
        data = {}
        with open(YAML_PATH) as f:
            conf = yaml.load(f, Loader=yaml.FullLoader)
            ions = parse_selected_species(ions)

            if cross_sections and (1,0) not in ions:
                logger.warning('Selecting H 0 required to ingest cross-sections.')
                ions.insert(0, (1,0))

            for ion in ions:
                symbol = convert_atomic_number2symbol(ion[0])

                try:
                    ion_keys = conf['atom'][symbol]['ion_charge'][ion[1]]
                    BASE_PATH = ATOMIC_PATH.joinpath(CMFGEN_DICT[symbol],
                                                     roman.toRoman(ion[1]+1),
                                                     ion_keys['date'])

                    logger.info(f'Configuration schema found for {symbol} {ion[1]}.')

                except KeyError:
                    continue

                osc_fname = BASE_PATH.joinpath(ion_keys['osc']
                                                ).as_posix()

                data[ion] = {}
                lvl_parser = CMFGENEnergyLevelsParser(osc_fname)
                lns_parser = CMFGENOscillatorStrengthsParser(osc_fname)
                data[ion]['levels'] = lvl_parser.base
                data[ion]['lines'] = lns_parser.base

                if cross_sections:
                    pho_flist = []
                    try:
                        for j, k in enumerate(ion_keys['pho']):
                            pho_fname = BASE_PATH.joinpath(ion_keys['pho'][j]).as_posix()
                            pho_flist.append(pho_fname)

                    except KeyError:
                        logger.warning(f'No `pho` data for {symbol} {ion[1]}.')

                    data[ion]['phixs'] = []
                    for l in pho_flist:
                        pho_parser = CMFGENPhotoionizationCrossSectionParser(l)
                        data[ion]['phixs'].append(pho_parser.base)

                    if ion == (1,0):
                        hyd_fname = BASE_PATH.joinpath('hyd_l_data.dat').as_posix()
                        gbf_fname = BASE_PATH.joinpath('gbf_n_data.dat').as_posix()

                        hyd_parser = CMFGENHydLParser(hyd_fname)
                        gbf_parser = CMFGENHydGauntBfParser(gbf_fname)

                        data[ion]['hyd'] = hyd_parser.base
                        data[ion]['gbf'] = gbf_parser.base

        return cls(data, priority)

    @staticmethod
    def cross_sections_squeeze(reader_phixs, ion_levels,
                               hyd_phixs_energy_grid_ryd, hyd_phixs,
                               hyd_gaunt_energy_grid_ryd, hyd_gaunt_factor):
        """ Docstring """

        phixs_table_list = []
        n_targets = len(reader_phixs)

        for i in range(n_targets):

            target = reader_phixs[i]
            lower_level_label = target.attrs['Configuration name']
            cross_section_type = target.attrs['Type of cross-section']

            # Remove the "[J]" term from J-splitted levels labels
            ion_levels['label'] = ion_levels['label'].str.rstrip(']')
            ion_levels['label'] = ion_levels['label'].str.split('[', expand=True)

            try:
                match = ion_levels.set_index('label').loc[[lower_level_label]]

            except KeyError:
                logger.warning(f'Level not found: \'{lower_level_label}\'.')
                continue

            lambda_angstrom = match['Lam(A)'].tolist()
            level_number = (match['ID'] -1).tolist()

            # Get statistical weights for J-splitted levels
            match['w'] = match['g']/match.sum()['g']
            w = match['w'].tolist()

            # match is > 1 just for J-splitted levels
            for j in range(len(match)):
                threshold_energy_ryd = HC_IN_EV_ANGSTROM / lambda_angstrom[j] / RYD_TO_EV

                if cross_section_type == 0:
                    phixs_table = get_null_phixs_table()

                elif cross_section_type in [20, 21, 22]:
                    diff = target['energy'].diff().dropna()
                    assert (diff >= 0).all()

                    energy = (target['energy']*threshold_energy_ryd).values
                    sigma = target['sigma'].values
                    phixs_table = np.column_stack((energy, sigma))

                elif cross_section_type in [1, 7]:
                    fit_coeff_list = target['fit_coeff'].to_list()

                    if len(fit_coeff_list) not in [1,3,4]:
                        logger.warning(f'Inconsistent number of fit coefficients for \'{lower_level_label}\'.')
                        continue

                    if len(fit_coeff_list) == 1 and fit_coeff_list[0] == 0.0:
                        phixs_table = get_null_phixs_table()

                    else:
                        phixs_table = get_seaton_phixs_table(threshold_energy_ryd, *fit_coeff_list)

                elif cross_section_type == 3:
                    fit_coeff_list = target['fit_coeff'].to_list()

                    if len(fit_coeff_list) != 2:
                        logger.warning(f'Inconsistent number of fit coefficients for \'{lower_level_label}\'.')
                        continue

                    scale, n = fit_coeff_list
                    phixs_table = scale * get_hydrogenic_n_phixs_table(hyd_gaunt_energy_grid_ryd, hyd_gaunt_factor,
                                                                        threshold_energy_ryd, n)

                elif cross_section_type in [2, 8]:
                    fit_coeff_list = target['fit_coeff'].to_list()
                    fit_coeff_list[0:3] = [int(x) for x in fit_coeff_list[0:3]]

                    if len(fit_coeff_list) not in [3,4]:
                        logger.warning(f'Inconsistent number of fit coefficients for \'{lower_level_label}\'.')
                        continue

                    phixs_table = get_hydrogenic_nl_phixs_table(hyd_phixs_energy_grid_ryd, hyd_phixs,
                                                                    threshold_energy_ryd, *fit_coeff_list)

                elif cross_section_type == 5:
                    fit_coeff_list = target['fit_coeff'].to_list()

                    if len(fit_coeff_list) != 5:
                        logger.warning(f'Inconsistent number of fit coefficients for \'{lower_level_label}\'.')
                        continue

                    phixs_table = get_opproject_phixs_table(threshold_energy_ryd, *fit_coeff_list)

                elif cross_section_type == 6:
                    fit_coeff_list = target['fit_coeff'].to_list()

                    if len(fit_coeff_list) != 8:
                        logger.warning(f'Inconsistent number of fit coefficients for \'{lower_level_label}\'.')
                        continue

                    phixs_table = get_hummer_phixs_table(threshold_energy_ryd, *fit_coeff_list)

                elif cross_section_type == 9:
                    fit_coeff_table = target

                    if fit_coeff_table.shape[1] != 8:
                        logger.warning(f'Inconsistent number of fit coefficients for \'{lower_level_label}\'.')
                        continue

                    phixs_table = get_vy95_phixs_table(threshold_energy_ryd, fit_coeff_table)

                elif cross_section_type == 4:
                    fit_coeff_list = target['fit_coeff'].tolist()

                    if len(fit_coeff_list) != 6:
                        logger.warning(f'Inconsistent number of fit coefficients for \'{lower_level_label}\'.')
                        continue

                    try:
                        phixs_table = get_leibowitz_phixs_table(threshold_energy_ryd, *fit_coeff_list)

                    except NotImplementedError:
                        logger.warning(f'Leibowitz\'s cross-section type 4 not implemented yet.')
                        phixs_table = get_null_phixs_table()

                else:
                    logger.warning(f'Unknown cross-section type {cross_section_type} for configuration \'{lower_level_label}\'.')
                    continue

                df = pd.DataFrame(phixs_table, columns=['energy', 'sigma'])
                df['level_index'] = level_number[j]
                df['sigma'] = w[j]*df['sigma']

                phixs_table_list.append(df)

        ion_phixs_table = pd.concat(phixs_table_list)

        return ion_phixs_table

    def _get_levels_lines(self, data):
        """ Generates `levels`, `lines` and `collisions` DataFrames.

        Parameters
        ----------
        data : dict
            Dictionary containing one dictionary per specie with 
            keys `levels`, `lines` and (optionally) `collisions`.
        """

        lvl_list = []
        lns_list = []
        pxs_list = []

        for ion, reader in data.items():
            atomic_number = ion[0]
            ion_charge = ion[1]

            symbol = convert_atomic_number2symbol(ion[0])
            logger.info(f'Loading atomic data for {symbol} {ion[1]}.')

            lvl = reader['levels']
            # some ID's have negative values (theoretical?)
            lvl.loc[ lvl['ID'] < 0, 'method'] = 'theor'
            lvl.loc[ lvl['ID'] > 0, 'method'] = 'meas'
            lvl['ID'] = np.abs(lvl['ID'])
            lvl_id = lvl.set_index('ID')

            lvl['atomic_number'] = atomic_number
            lvl['ion_charge'] =  ion_charge 
            lvl_list.append(lvl)

            lns = reader['lines']
            lns = lns.set_index(['i', 'j'])
            lns['energy_lower'] = lvl_id['E(cm^-1)'].reindex(lns.index, level=0).values
            lns['energy_upper'] = lvl_id['E(cm^-1)'].reindex(lns.index, level=1).values
            lns['g_lower'] = lvl_id['g'].reindex(lns.index, level=0).values
            lns['g_upper'] = lvl_id['g'].reindex(lns.index, level=1).values
            lns['j_lower'] = (lns['g_lower'] -1)/2
            lns['j_upper'] = (lns['g_upper'] -1)/2
            lns['atomic_number'] = atomic_number
            lns['ion_charge'] = ion_charge
            lns = lns.reset_index()
            lns_list.append(lns)

            if 'phixs' in reader.keys():
                if ion == (1,0):
                    
                    n_levels = 30
                    l_points, l_start_u, l_del_u = 97, 0.0, 0.041392685
                    n_points, n_start_u, n_del_u = 145, 0.0, 0.041392685

                    hyd = reader['hyd'].apply(lambda x: 10 ** (8 + x))
                    gbf = reader['gbf']

                    hyd_phixs, hyd_phixs_energy_grid_ryd = {}, {}
                    hyd_gaunt_factor, hyd_gaunt_energy_grid_ryd = {}, {}

                    for n in range(1, n_levels+1):

                        lambda_angstrom = lvl.loc[n-1, 'Lam(A)']
                        e_threshold_ev = HC_IN_EV_ANGSTROM / lambda_angstrom

                        hyd_gaunt_energy_grid_ryd[n] = [e_threshold_ev / RYD_TO_EV * 10 ** (n_start_u + n_del_u * i) for i in range(n_points)]
                        hyd_gaunt_factor[n] = gbf.loc[n].tolist()

                        for l in range(0, n):
                            hyd_phixs_energy_grid_ryd[(n, l)] = [e_threshold_ev / RYD_TO_EV * 10 ** (l_start_u + l_del_u * i) for i in range(l_points)]
                            hyd_phixs[(n,l)] = hyd.loc[(n,l)].tolist()

                pxs = self.cross_sections_squeeze(reader['phixs'][0], lvl, hyd_phixs_energy_grid_ryd, hyd_phixs, hyd_gaunt_energy_grid_ryd, hyd_gaunt_factor)
                pxs['atomic_number'] = ion[0]
                pxs['ion_charge'] = ion[1]
                pxs_list.append(pxs)

        levels = pd.concat(lvl_list)
        levels['priority'] = self.priority
        levels = levels.reset_index(drop=False)
        levels = levels.rename(columns={'label': 'label', 
                                        'E(cm^-1)': 'energy', 
                                        'index': 'level_index'})
        levels['j'] = (levels['g'] -1) / 2
        levels = levels.set_index(['atomic_number', 'ion_charge', 'level_index'])
        levels = levels[['energy', 'j', 'label', 'method', 'priority']]
        
        lines = pd.concat(lns_list)
        lines = lines.rename(columns={'Lam(A)': 'wavelength'})
        lines['wavelength'] = u.Quantity(lines['wavelength'], u.AA).to('nm').value
        lines['level_index_lower'] = lines['i'] -1
        lines['level_index_upper'] = lines['j'] -1
        lines['gf'] = lines['f'] * lines['g_lower']
        lines = lines.set_index(['atomic_number', 'ion_charge', 
                                 'level_index_lower', 'level_index_upper'])
        lines = lines[['energy_lower', 'energy_upper', 
                       'gf', 'j_lower', 'j_upper', 'wavelength']]

        if 'phixs' in reader.keys():
            cross_sections = pd.concat(pxs_list)
            cross_sections = cross_sections.set_index(['atomic_number', 'ion_charge', 'level_index'])
            self.cross_sections = cross_sections.sort_index()

        self.levels = levels
        self.lines = lines

        return
