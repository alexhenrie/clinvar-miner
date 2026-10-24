#!/usr/bin/env python3

import itertools as it

print('Creating indexes')

def create_index(cursor, table, columns):
    index = table + '__' + '__'.join(columns)
    columns = ','.join(columns)
    cursor.execute(f'CREATE INDEX IF NOT EXISTS {index} ON {table} ({columns})')

db = __import__('import-clinvar-xml').connect()
cursor = db.cursor()

submission_columns_to_index = [
    'rsid',
    'gene',
    'normalized_gene',
    'rcv',
    'submitter_id',
    'submitter_name',
    'submitter_country_code',
    'significance',
    'condition_name',
    'method',
]
create_index(cursor, 'submissions', ['date'])
for column in submission_columns_to_index:
    create_index(cursor, 'submissions', [column])
    create_index(cursor, 'submissions', ['date', column])

#front page
create_index(cursor, 'comparisons', ['date', 'conflict_level', 'scv1'])

#many pages are filtered by conflict_level=-1 by default as an optimization
for first_cols in (['date'], ['date', 'conflict_level']):
    #total submissions by method
    create_index(cursor, 'comparisons', first_cols + ['method1', 'scv1'])

    #total submissions by country
    create_index(cursor, 'comparisons', first_cols + ['submitter1_country_code', 'scv1'])
    create_index(cursor, 'comparisons', first_cols + ['submitter1_country_code', 'submitter1_id', 'scv1'])

    #submissions by variant
    create_index(cursor, 'comparisons', first_cols + ['variant_name', 'scv1'])

    for gene_col in ('gene', 'normalized_gene'):
        categories = (gene_col, 'condition1_name', 'submitter1_id')

        for significance_col in ('significance', 'normalized_significance'):
            #variants by significance
            for category in categories:
                create_index(cursor, 'comparisons', first_cols + [significance_col + '1', category, 'variant_name'])

            #variants by gene, condition, submitter
            for category_permutation in it.permutations(categories, 2):
                create_index(cursor, 'comparisons', first_cols + list(category_permutation) + [significance_col + '1', 'variant_name'])

            for conflict_level_col in ('conflict_level', 'normalized_conflict_level'):
                #variants in conflict by significance
                create_index(cursor, 'comparisons', ['date', conflict_level_col, 'variant_name'])
                create_index(cursor, 'comparisons', ['date', significance_col + '1', significance_col + '2', conflict_level_col, 'variant_name'])

                #variants in conflict by gene, condition, submitter
                for category in categories:
                    create_index(cursor, 'comparisons', ['date', category, conflict_level_col, 'variant_name'])
                    create_index(cursor, 'comparisons', ['date', category, significance_col + '1', significance_col + '2', conflict_level_col, 'variant_name'])

                #variants in conflict by submitter pair
                create_index(cursor, 'comparisons', ['date', 'submitter1_id', 'submitter2_id', conflict_level_col, 'variant_name'])
                create_index(cursor, 'comparisons', ['date', 'submitter1_id', 'submitter2_id', significance_col + '1', significance_col + '2', conflict_level_col, 'variant_name'])

create_index(cursor, 'mondo_clinvar_relationships', ['mondo_id'])


date = list(cursor.execute('SELECT MAX(date) FROM submissions'))[0][0]


print('Creating gene links table')

for normalized in (True, False):
    if normalized:
        table = 'normalized_gene_links'
        gene_column = 'normalized_gene'
        type_column = 'normalized_gene_type'
    else:
        table = 'gene_links'
        gene_column = 'gene'
        type_column = 'gene_type'

    cursor.execute('DROP TABLE IF EXISTS ' + table)

    cursor.execute('CREATE TABLE ' + table + ' (gene TEXT, see_also TEXT)')

    query = 'SELECT DISTINCT ' + gene_column + ' FROM submissions WHERE ' + type_column + '=2 AND date=?'
    gene_combinations = list(map(lambda row: row[0], cursor.execute(query, [date])))

    query = 'SELECT 1 FROM submissions WHERE ' + gene_column + '=? AND date=?'
    for gene_combination in gene_combinations:
        for individual_gene in gene_combination.split(', '):
            is_gene = bool(list(cursor.execute(query, [individual_gene, date])))
            if is_gene:
                cursor.executemany(
                    'INSERT INTO ' + table + ' VALUES (?,?)',
                    [[gene_combination, individual_gene], [individual_gene, gene_combination]]
                )

    cursor.execute('CREATE INDEX ' + table + '__gene ON ' + table + ' (gene)')

db.commit()
db.close()
