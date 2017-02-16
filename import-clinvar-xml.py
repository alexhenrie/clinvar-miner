#!/usr/bin/env python3

from collections import OrderedDict
from itertools import combinations
from os.path import basename
from sys import argv
from xml.etree import ElementTree
import re
import sqlite3

if len(argv) < 2:
    print('Usage: ./import-clinvar-xml.py ClinVarFullRelease_<year>-<month>.xml ...')
    exit()

nonstandard_significance_term_map = dict(map(
    lambda line: line[0:-1].split('\t'),
    open('nonstandard_significance_terms.tsv')
))

def connect():
    return sqlite3.connect('clinvar.db', timeout=600)

def create_tables():
    db = connect()
    cursor = db.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            date TEXT,
            ncbi_variation_id TEXT,
            preferred_name TEXT,
            variant_type TEXT,
            gene_symbol TEXT,
            submitter_id TEXT,
            submitter_name TEXT,
            rcv TEXT,
            scv TEXT,
            clin_sig TEXT,
            corrected_clin_sig TEXT,
            last_eval TEXT,
            review_status TEXT,
            sub_condition TEXT,
            method TEXT,
            description TEXT,
            PRIMARY KEY (date, scv)
        )
    ''')

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS conflicting_submissions AS
        SELECT DISTINCT t1.date AS date, t1.ncbi_variation_id AS ncbi_variation_id, t1.preferred_name as preferred_name,
        t1.variant_type AS variant_type, t1.gene_symbol AS gene_symbol, t1.submitter_id AS submitter_id,
        t1.submitter_name AS submitter_name, t1.rcv AS rcv, t1.scv AS scv, t1.clin_sig AS clin_sig,
        t1.corrected_clin_sig AS corrected_clin_sig, t1.last_eval AS last_eval, t1.review_status AS review_status,
        t1.sub_condition AS sub_condition, t1.method AS method, t1.description AS description
        FROM submissions t1 INNER JOIN submissions t2
        ON t1.date=t2.date AND t1.ncbi_variation_id=t2.ncbi_variation_id
        WHERE t1.corrected_clin_sig!=t2.corrected_clin_sig
    ''')

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS conflicts AS
        SELECT t1.date AS date, t1.ncbi_variation_id AS ncbi_variation_id, t1.preferred_name AS preferred_name,
        t1.variant_type AS variant_type, t1.gene_symbol AS gene_symbol, t1.submitter_id AS submitter1_id,
        t1.submitter_name AS submitter1_name, t1.rcv AS rcv1, t1.scv AS scv1, t1.clin_sig AS clin_sig1,
        t1.corrected_clin_sig AS corrected_clin_sig1, t1.last_eval AS last_eval1, t1.review_status AS review_status1,
        t1.sub_condition AS sub_condition1, t2.method AS method1, t1.description AS description1,
        t2.submitter_id AS submitter2_id, t2.submitter_name AS submitter2_name, t2.rcv AS rcv2, t2.scv AS scv2,
        t2.clin_sig AS clin_sig2, t2.corrected_clin_sig AS corrected_clin_sig2, t2.last_eval AS last_eval2,
        t2.review_status AS review_status2, t2.sub_condition AS sub_condition2, t2.method AS method2,
        t2.description AS description2
        FROM submissions t1 INNER JOIN submissions t2
        ON t1.date=t2.date AND t1.ncbi_variation_id=t2.ncbi_variation_id
        WHERE t1.corrected_clin_sig!=t2.corrected_clin_sig
    ''')

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS current_submissions AS
        SELECT * FROM submissions WHERE date=(
            SELECT MAX(date) FROM submissions
        )
    ''')

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS current_conflicting_submissions AS
        SELECT * FROM conflicting_submissions WHERE date=(
            SELECT MAX(date) FROM submissions
        )
    ''')

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS current_conflicts AS
        SELECT * FROM conflicts WHERE date=(
            SELECT MAX(date) FROM submissions
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS date_index ON submissions (date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS ncbi_variation_id_index ON submissions (ncbi_variation_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS preferred_name_index ON submissions (preferred_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS gene_symbol_index ON submissions (gene_symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS submitter_id_index ON submissions (submitter_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS submitter_name_index ON submissions (submitter_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS clin_sig_index ON submissions (clin_sig)')
    cursor.execute('CREATE INDEX IF NOT EXISTS corrected_clin_sig_index ON submissions (corrected_clin_sig)')
    cursor.execute('CREATE INDEX IF NOT EXISTS method_index ON submissions (method)')
    cursor.execute('CREATE INDEX IF NOT EXISTS date_ncbi_variation_id_index ON submissions (date, ncbi_variation_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS date_method_index ON submissions (date, method)')

def import_file(filename):
    matches = re.fullmatch(r'ClinVarFullRelease_(\d\d\d\d-\d\d).xml', basename(filename))
    if matches:
        print('Importing ' + filename)
    else:
        print('Skipped unrecognized filename ' + filename)
        return

    date = matches.group(1)
    submissions = []

    #extract submission information
    for event, set_el in ElementTree.iterparse(filename):
        if set_el.tag != 'ClinVarSet':
            continue

        reference_assertion_el = set_el.find('./ReferenceClinVarAssertion')
        measure_set_el = reference_assertion_el.find('./MeasureSet')
        preferred_name_el = measure_set_el.find('./Name/ElementValue[@Type="Preferred"]')
        measure_el = measure_set_el.find('./Measure')
        gene_symbol_el = measure_el.find('./MeasureRelationship/Symbol/ElementValue[@Type="Preferred"]')

        for assertion_el in set_el.findall('./ClinVarAssertion'):
            scv_el = assertion_el.find('./ClinVarAccession[@Type="SCV"]')
            scv = scv_el.attrib['Acc']

            submission_id_el = assertion_el.find('./ClinVarSubmissionID')
            clin_sig_el = assertion_el.find('./ClinicalSignificance')
            description_el = clin_sig_el.find('./Description')
            review_status_el = clin_sig_el.find('./ReviewStatus')
            sub_condition_el = assertion_el.find('./TraitSet[@Type="PhenotypeInstruction"]/Trait[@Type="PhenotypeInstruction"]/Name/ElementValue[@Type="Preferred"]')
            method_el = assertion_el.find('./ObservedIn/Method/MethodType')
            comment_el = clin_sig_el.find('./Comment')

            ncbi_variation_id = measure_set_el.attrib['ID']
            preferred_name = preferred_name_el.text if preferred_name_el != None else '' #missing in old versions
            variant_type = measure_el.attrib['Type']
            gene_symbol = gene_symbol_el.text if gene_symbol_el != None else ''
            submitter_id = scv_el.attrib.get('OrgID', '') #missing in old versions
            submitter_name = submission_id_el.get('submitter', '') if submission_id_el != None else '' #missing in old versions
            rcv = reference_assertion_el.find('./ClinVarAccession[@Type="RCV"]').attrib['Acc']
            clin_sig = description_el.text.lower() if description_el != None else 'not provided'
            corrected_clin_sig = nonstandard_significance_term_map.get(clin_sig, clin_sig)
            last_eval = clin_sig_el.attrib.get('DateLastEvaluated', '') #missing in old versions
            review_status = review_status_el.text if review_status_el != None else '' #missing in old versions
            sub_condition = sub_condition_el.text if sub_condition_el != None else ''
            method = method_el.text if method_el != None else 'not provided' #missing in old versions
            description = comment_el.text if comment_el != None else ''

            submissions.append((
                date,
                ncbi_variation_id,
                preferred_name,
                variant_type,
                gene_symbol,
                submitter_id,
                submitter_name,
                rcv,
                scv,
                clin_sig,
                corrected_clin_sig,
                last_eval,
                review_status,
                sub_condition,
                method,
                description,
            ))

        set_el.clear() #conserve memory

    #do all the database imports at once to minimize the time that we hold the database lock

    db = connect()
    cursor = db.cursor()

    cursor.executemany(
        'INSERT OR IGNORE INTO submissions VALUES (' + ','.join('?' * len(submissions[0])) + ')', submissions
    )

    db.commit()
    db.close()

create_tables()
for filename in argv[1:]:
    import_file(filename)
