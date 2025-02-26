import importlib.metadata
from pathlib import Path

import numpy as np
import packaging
import pandas as pd
import pytest

from pyam import IamDataFrame, read_datapackage
from pyam.netcdf import read_netcdf
from pyam.testing import assert_iamframe_equal
from pyam.utils import META_IDX

from .conftest import META_DF, TEST_DATA_DIR

try:
    import xlrd  # noqa: F401

    has_xlrd = True
except ModuleNotFoundError:  # pragma: no cover
    has_xlrd = False

try:
    import python_calamine  # noqa: F401

    has_calamine = True
except ModuleNotFoundError:  # pragma: no cover
    has_calamine = False


FILTER_ARGS = dict(scenario="scen_a")


def test_data_none():
    # initializing with 'data=None' raises an error
    match = "IamDataFrame constructor not properly called!"
    with pytest.raises(ValueError, match=match):
        IamDataFrame(None)


def test_unknown_type():
    # initializing with unsupported argument type raises an error
    match = "IamDataFrame constructor not properly called!"
    with pytest.raises(ValueError, match=match):
        IamDataFrame(True)


def test_not_a_file():
    # initializing with a file-like that's not a file raises an error
    match = "No such file: 'foo.csv'"
    with pytest.raises(FileNotFoundError, match=match):
        IamDataFrame("foo.csv")


def test_io_list():
    # initializing with a list raises an error
    match = "Initializing from list is not supported,"
    with pytest.raises(ValueError, match=match):
        IamDataFrame([1, 2])


def test_io_csv_to_file(test_df, tmpdir):
    # write to csv
    file = tmpdir / "testing_io_write_read.csv"
    test_df.to_csv(file)

    # read from csv and assert that `data` tables are equal
    import_df = IamDataFrame(file)
    pd.testing.assert_frame_equal(test_df.data, import_df.data)


def test_io_csv_none(test_df_year):
    # parse data as csv and return as string
    exp = (
        "Model,Scenario,Region,Variable,Unit,2005,2010\n"
        "model_a,scen_a,World,Primary Energy,EJ/yr,1.0,6.0\n"
        "model_a,scen_a,World,Primary Energy|Coal,EJ/yr,0.5,3.0\n"
        "model_a,scen_b,World,Primary Energy,EJ/yr,2.0,7.0\n"
    )
    assert test_df_year.to_csv(lineterminator="\n") == exp


@pytest.mark.parametrize(
    "meta_args", [[{}, {}], [dict(include_meta="foo"), dict(meta_sheet_name="foo")]]
)
def test_io_xlsx(test_df, meta_args, tmpdir):
    # write to xlsx (direct file name and ExcelWriter, see #300)
    file = tmpdir / "testing_io_write_read.xlsx"
    for f in [file, pd.ExcelWriter(file)]:
        test_df.to_excel(f, **meta_args[0])
        if isinstance(f, pd.ExcelWriter):
            f.close()

        # read from xlsx
        import_df = IamDataFrame(file, **meta_args[1])

        # assert that IamDataFrame instances are equal
        assert_iamframe_equal(test_df, import_df)


@pytest.mark.parametrize(
    "sheets, sheetname",
    [
        [["data1", "Data2"], {}],
        [["data1", "data2"], dict(sheet_name="data*")],
        [["data1", "foo"], dict(sheet_name=["data*", "foo"])],
    ],
)
def test_io_xlsx_multiple_data_sheets(test_df, sheets, sheetname, tmpdir):
    # write data to separate sheets in excel file
    file = tmpdir / "testing_io_write_read.xlsx"
    xl = pd.ExcelWriter(file, engine="xlsxwriter")
    for i, (model, scenario) in enumerate(test_df.index):
        test_df.filter(scenario=scenario).to_excel(xl, sheet_name=sheets[i])
    test_df.export_meta(xl)
    xl.close()

    # read from xlsx
    import_df = IamDataFrame(file, **sheetname)

    # assert that IamDataFrame instances are equal
    assert_iamframe_equal(test_df, import_df)


@pytest.mark.skipif(not has_xlrd, reason="Package 'xlrd' not installed.")
def test_read_xls(test_df_year):
    import_df = IamDataFrame(TEST_DATA_DIR / "test_df.xls")
    assert_iamframe_equal(test_df_year, import_df)


@pytest.mark.skipif(
    packaging.version.parse(importlib.metadata.version("pandas"))
    < packaging.version.parse("2.2.0"),
    reason="pandas < 2.2.0 has inconsistent support for `engine_kwargs`",
)
def test_read_xlsx_kwargs(test_df_year):
    # Test that kwargs to `IamDataFrame.__init__` are passed to `pd.read_excel`
    # or `pd.ExcelFile` when reading an Excel file. The `engine_kwargs`
    # here does not really do anything, but is included to make sure that using
    # it doesn't crash anything, which would be a sign that it's not being
    # passed correctly to `pd.ExcelFile`.
    import_df = IamDataFrame(
        TEST_DATA_DIR / "test_df.xlsx",
        sheet_name="custom data sheet name",
        nrows=2,
        engine="openpyxl",
        engine_kwargs={"data_only": False},
    )
    assert_iamframe_equal(
        test_df_year.filter(scenario="scen_a"),
        import_df,
    )


@pytest.mark.skipif(not has_calamine, reason="Package 'python_calamine' not installed.")
@pytest.mark.skipif(
    packaging.version.parse(importlib.metadata.version("pandas"))
    < packaging.version.parse("2.2.0"),
    reason="`engine='calamine' requires pandas >= 2.2.0",
)
def test_read_xlsx_calamine(test_df_year):
    # Test that an xlsx file is read correctly when using the calamine engine,
    # and that excel kwargs such as `sheet_name` are still handled correctly
    import_df = IamDataFrame(
        TEST_DATA_DIR / "test_df.xlsx",
        engine="calamine",
        sheet_name="custom data sheet name",
    )
    assert_iamframe_equal(import_df, test_df_year)


def test_init_df_with_na_unit(test_pd_df, tmpdir):
    # missing values in the unit column are replaced by an empty string
    test_pd_df.loc[1, "unit"] = np.nan
    df = IamDataFrame(test_pd_df)
    assert df.unit == ["", "EJ/yr"]

    # writing to file and importing as pandas returns `nan`, not empty string
    file = tmpdir / "na_unit.csv"
    df.to_csv(file)
    df_csv = pd.read_csv(file)
    assert np.isnan(df_csv.loc[1, "Unit"])
    IamDataFrame(file)  # reading from file as IamDataFrame works

    file = tmpdir / "na_unit.xlsx"
    df.to_excel(file)
    df_excel = pd.read_excel(file, engine="openpyxl")
    assert np.isnan(df_excel.loc[1, "Unit"])
    IamDataFrame(file)  # reading from file as IamDataFrame works


def test_init_df_with_na_column_raises(test_pd_df, tmpdir):
    # reading from file with a "corrupted" column raises expected error
    match = r"Empty cells in `data` \(columns: 'unnamed: 7'\):"
    with pytest.raises(ValueError, match=match):
        IamDataFrame(TEST_DATA_DIR / "na_column.xlsx")


@pytest.mark.parametrize(
    "sheet_name, init_args, rename",
    [
        ("meta", {}, False),
        ("meta", dict(sheet_name="meta"), False),
        ("foo", dict(sheet_name="foo"), False),
        ("foo", dict(sheet_name="foo"), True),
    ],
)
def test_load_meta_xlsx(test_pd_df, sheet_name, init_args, rename, tmpdir):
    """Test loading meta from an Excel file"""
    # downselect meta
    meta = META_DF.iloc[0:1] if rename else META_DF

    # initialize a new IamDataFrame directly from data and meta
    exp = IamDataFrame(test_pd_df, meta=meta)

    # write meta to file (without an exclude col)
    file = tmpdir / "testing_io_meta.xlsx"
    meta.reset_index().to_excel(file, sheet_name=sheet_name, index=False)

    # initialize a new IamDataFrame and load meta from file
    obs = IamDataFrame(test_pd_df)
    obs.load_meta(file)

    assert_iamframe_equal(obs, exp)


@pytest.mark.parametrize("rename", [True, False])
def test_load_meta_csv(test_pd_df, rename, tmpdir):
    """Test loading meta from an csv file"""
    meta = META_DF.iloc[0:1] if rename else META_DF

    # initialize a new IamDataFrame directly from data and meta
    exp = IamDataFrame(test_pd_df, meta=meta)

    # write meta to file (without an exclude col)
    file = tmpdir / "testing_io_meta.csv"
    meta.reset_index().to_csv(file, index=False)

    # initialize a new IamDataFrame and load meta from file
    obs = IamDataFrame(test_pd_df)
    obs.load_meta(file)

    assert_iamframe_equal(obs, exp)


def test_load_meta_wrong_index(test_df_year, tmpdir):
    """Loading meta without (at least) index cols as headers raises an error"""

    # write meta frame with wrong index to file, then load to the IamDataFrame
    file = tmpdir / "testing_meta_empty.xlsx"
    pd.DataFrame(columns=["model", "foo"]).to_excel(file, index=False)

    match = r"Missing index columns for meta indicators: \['scenario'\]"
    with pytest.raises(ValueError, match=match):
        test_df_year.load_meta(file)


def test_load_meta_empty_rows(test_df_year, tmpdir):
    """Loading empty meta table (columns but no rows) from xlsx file"""
    exp = test_df_year.copy()  # loading empty file has no effect

    # write empty meta frame to file, then load to the IamDataFrame
    file = tmpdir / "testing_meta_empty.xlsx"
    pd.DataFrame(columns=META_IDX).to_excel(file, index=False)
    test_df_year.load_meta(file)

    assert_iamframe_equal(test_df_year, exp)


def test_load_meta_exclude(test_pd_df):
    """Initializing from xlsx where 'meta' has an exclude columns (pyam < 2.0)"""
    obs = IamDataFrame(TEST_DATA_DIR / "exclude_meta_sheet.xlsx")
    exp = IamDataFrame(test_pd_df)
    exp.exclude.iloc[0] = True
    assert_iamframe_equal(obs, exp)


def test_load_meta_empty(test_pd_df):
    """Initializing from xlsx where 'meta' has no rows and non-empty invisible header"""
    obs = IamDataFrame(TEST_DATA_DIR / "empty_meta_sheet.xlsx")
    exp = IamDataFrame(test_pd_df)
    assert_iamframe_equal(obs, exp)


def test_load_ssp_database_downloaded_file(test_pd_df):
    exp = IamDataFrame(test_pd_df).filter(**FILTER_ARGS).as_pandas()
    file = TEST_DATA_DIR / "test_SSP_database_raw_download.xlsx"
    obs_df = IamDataFrame(file)
    pd.testing.assert_frame_equal(obs_df.as_pandas(), exp)


def test_load_rcp_database_downloaded_file(test_pd_df):
    exp = IamDataFrame(test_pd_df).filter(**FILTER_ARGS).as_pandas()
    file = TEST_DATA_DIR / "test_RCP_database_raw_download.xlsx"
    obs_df = IamDataFrame(file)
    pd.testing.assert_frame_equal(obs_df.as_pandas(), exp)


def test_io_datapackage(test_df, tmpdir):
    # add column to `meta` and write to datapackage
    file = Path(tmpdir) / "foo.zip"
    test_df.set_meta(["a", "b"], "string")
    test_df.to_datapackage(file)

    # read from csv assert that IamDataFrame instances are equal
    import_df = read_datapackage(file)
    assert_iamframe_equal(test_df, import_df)


def test_io_netcdf(test_df, tmpdir):
    file = Path(tmpdir) / "foo.nc"
    test_df.to_netcdf(file)
    assert_iamframe_equal(read_netcdf(file), test_df)
