import json
from pathlib import Path
from tempfile import TemporaryDirectory

from issue.catalog import IssueCatalog, issue
from receipt.intake import receive
from receipt.inventory import ReceiptInventory
from reports.history import read
from reports.store import ReportStore
from review.assessment import review
from survey.reference import online
from survey.revision_store import RevisionStore
from survey.revisions import freeze


SAMPLES = Path(__file__).resolve().parent / 'samples'


def _outcome(bundle):
    return json.loads(bundle.report)['outcome']


def _scenario(case_id, inputs, expected, actual, stored, code_paths, oracle):
    if expected != actual or expected != stored:
        raise AssertionError(f'{case_id}: expected {expected}, observed {actual}, stored {stored}')
    evidence = {
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': expected, 'downstream_actual': stored,
        'code_paths': code_paths, 'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, sort_keys=True))


def main():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / 'source'
        source.mkdir()
        center = root / 'center.sqlite'
        revisions = RevisionStore(source / 'station.sqlite')
        catalog = IssueCatalog(source / 'station.sqlite')
        inventory = ReceiptInventory(center)
        reports = ReportStore(center)
        for store in (revisions, catalog, inventory, reports):
            store.initialize()

        prepared = {}
        expected = {
            'early.json': {'kind': 'loop', 'entry_hops': 1, 'loop_length': 3},
            'control.json': {'kind': 'loop', 'entry_hops': 2, 'loop_length': 3},
        }
        outlet = {'kind': 'outlet', 'outlet': 'O', 'hops': 4}
        for name, loop in expected.items():
            data = json.loads((SAMPLES / name).read_text(encoding='utf-8'))
            revision = freeze(revisions, data)
            if online(revisions, revision, 'S').as_record() != loop:
                raise AssertionError(f'unexpected online loop in {name}')
            if online(revisions, revision, 'T').as_record() != outlet:
                raise AssertionError(f'unexpected online outlet in {name}')
            received = {}
            for piece in data['pieces']:
                fixed = issue(revisions, catalog, revision, piece)
                if issue(None, catalog, issue_id=fixed.issue_id) != fixed:
                    raise AssertionError(f'reissue changed {name}/{piece}')
                received[piece] = receive(inventory, fixed.raw)
            prepared[name] = (data['survey'], revision, received)

        source.rename(root / 'disconnected-source')
        if source.exists():
            raise AssertionError('source directory is still attached')
        print('源目录已移走，中心按点名实收件签报。')
        actual = {}
        signed = {}
        for name, (survey, revision, received) in prepared.items():
            result = review(inventory, reports, survey, revision, received.values(), 'S')
            if result.provenance != tuple(sorted(received.items())):
                raise AssertionError(f'wrong receipt provenance for {name}')
            signed[name] = result
            actual[name] = _outcome(result)
            print(f'{name} S: {actual[name]}')

        survey, revision, received = prepared['early.json']
        drainage = review(inventory, reports, survey, revision, received.values(), 'T')
        print(f'early.json T: {_outcome(drainage)}')
        reopened = ReportStore(center)
        stored = {}
        for name, result in signed.items():
            original = read(reopened, result.report_id)
            if original != result:
                raise AssertionError(f'historical report changed for {name}')
            stored[name] = _outcome(original)
        stored_drainage = read(reopened, drainage.report_id)
        if stored_drainage != drainage:
            raise AssertionError('outlet report or first receipt changed')
        print('重开中心后，两份循环报告和排口报告均按原号复领。')

        _scenario('v9', {'start': 'S', 'samples': list(prepared), 'coverage': ['A', 'B']},
                  expected, actual, stored,
                  ['survey/reference.py', 'issue/evidence.py', 'review/trace.py', 'reports/history.py'],
                  '逐跳手算，提前版在第 1 和第 4 跳重访，对照版在第 2 和第 5 跳重访')
        _scenario('v5.seam_hops', {'start': 'T', 'sample': 'early.json', 'coverage': ['A', 'B']},
                  outlet, _outcome(drainage), _outcome(stored_drainage),
                  ['issue/segments.py', 'review/ports.py', 'review/trace.py', 'reports/history.py'],
                  '从 T 到接近格、乙幅格、回幅格、排口，各移动一跳')


if __name__ == '__main__':
    main()
