"""Recompute Global Superstore findings without exporting customer-level data.

Adapted from the verification notebook accompanying Henry Audi's Tableau project.
Run from the repository root; the input workbook is downloaded separately.
"""
import argparse
import json
from pathlib import Path
import pandas as pd

BANDS = ['No discount', 'Over 0%-10%', 'Over 10%-20%', 'Over 20%-30%', 'Over 30%-50%', 'Over 50%-100%']


def analyze(source, output):
    frame = pd.read_excel(source, sheet_name='Sheet1')
    source_columns = list(frame.columns)
    for column in ['Order Date', 'Ship Date']:
        frame[column] = pd.to_datetime(frame[column], format='%d-%m-%Y', errors='coerce')
    measures = ['Sales', 'Profit', 'Quantity', 'Discount', 'Shipping Cost']
    dimensions = ['Category', 'Sub-Category', 'Market', 'Region', 'Country', 'Segment']
    quality = {
        'rows': len(frame), 'source_fields': len(source_columns),
        'unique_row_ids': int(frame['Row ID'].nunique()),
        'missing_row_ids': int(frame['Row ID'].isna().sum()),
        'duplicate_records_excluding_row_id': int(frame.drop(columns='Row ID').duplicated().sum()),
        'missing_dates': int(frame[['Order Date', 'Ship Date']].isna().any(axis=1).sum()),
        'missing_required_measures': int(frame[measures].isna().any(axis=1).sum()),
        'missing_analysis_categories': int(frame[dimensions].apply(lambda c: c.isna() | c.astype(str).str.strip().eq('')).any(axis=1).sum()),
        'shipping_before_order': int((frame['Ship Date'] < frame['Order Date']).sum()),
        'invalid_discount': int((~frame['Discount'].between(0, 1)).sum()),
        'nonpositive_sales': int((frame['Sales'] <= 0).sum()),
        'invalid_quantity': int(((frame['Quantity'] <= 0) | frame['Quantity'].mod(1).ne(0)).sum()),
        'negative_shipping_cost': int((frame['Shipping Cost'] < 0).sum()),
        'missing_postal_codes': int(frame['Postal Code'].isna().sum()),
    }
    checks = [k for k in quality if k not in ['rows', 'source_fields', 'unique_row_ids', 'missing_postal_codes']]
    if any(quality[k] for k in checks) or quality['unique_row_ids'] != len(frame):
        raise ValueError(f'Data validation failed: {quality}')
    if len(frame) != 51290 or len(source_columns) != 24:
        raise ValueError('Expected the project source: 51,290 records and 24 fields.')
    frame['Discount Band'] = pd.cut(frame['Discount'], [-1, 0, .1, .2, .3, .5, 1], labels=BANDS, right=True)

    def aggregate(keys):
        result = frame.groupby(keys, observed=True).agg(rows=('Row ID', 'size'), sales=('Sales', 'sum'), profit=('Profit', 'sum'), average_discount=('Discount', 'mean'))
        result['profit_margin'] = result['profit'] / result['sales']
        return result.reset_index()

    bands = aggregate('Discount Band')
    products = aggregate('Sub-Category').sort_values('profit', ascending=False)
    markets = aggregate(['Market', 'Sub-Category'])
    frame['Month'] = frame['Order Date'].dt.to_period('M').astype(str)
    monthly = aggregate(['Month', 'Discount Band'])
    negative_months = monthly.assign(loss=monthly['profit'] < 0).groupby('Discount Band', observed=True)['loss'].sum()
    summary = {
        'rows': len(frame), 'sales': float(frame['Sales'].sum()), 'profit': float(frame['Profit'].sum()),
        'profit_margin': float(frame['Profit'].sum() / frame['Sales'].sum()),
        'start_date': str(frame['Order Date'].min().date()), 'end_date': str(frame['Order Date'].max().date()),
        'markets': int(frame['Market'].nunique()), 'subcategories': int(frame['Sub-Category'].nunique()),
        'months': int(frame['Month'].nunique()),
        'negative_months_by_discount_band': {str(k): int(v) for k, v in negative_months.items()},
    }
    # Reconcile the analysis to the saved Tableau project, with tolerance for floating-point sums.
    assert abs(summary['sales'] - 12642501.90988) < .01
    assert abs(summary['profit'] - 1467457.29128) < .01
    assert summary['months'] == 48
    assert all(summary['negative_months_by_discount_band'][k] == 48 for k in BANDS[-2:])
    assert abs(float(products.loc[products['Sub-Category'].eq('Tables'), 'profit'].iloc[0]) + 64083.3897) < 1
    output.mkdir(parents=True, exist_ok=True)
    for name, table in [('discount_bands', bands), ('subcategories', products), ('market_subcategories', markets), ('monthly_discount_bands', monthly)]:
        table.to_csv(output / f'{name}.csv', index=False, float_format='%.8f')
    for name, obj in [('summary', summary), ('data_quality', quality)]:
        (output / f'{name}.json').write_text(json.dumps(obj, indent=2) + '\n')
    print(f'Validated {len(frame):,} order lines; aggregate outputs written to {output}')
    print(f"Sales: {summary['sales']:,.2f}; profit: {summary['profit']:,.2f}; margin: {summary['profit_margin']:.1%}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('data/Global_Superstore2.xlsx'))
    parser.add_argument('--output', type=Path, default=Path('results'))
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f'Input workbook not found: {args.input}. See data/README.md for source instructions.')
    analyze(args.input, args.output)
