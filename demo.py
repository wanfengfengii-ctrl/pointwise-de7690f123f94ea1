import json
from pathlib import Path
from tempfile import TemporaryDirectory

from issue.catalog import IssueCatalog, issue, compatibility_for
from issue.declaration import digest_declaration
from receipt.intake import receive
from receipt.inventory import ReceiptInventory
from reports.history import read
from reports.store import ReportStore
from review.assessment import review, review_reuse
from reuse_cases import PIECES, seam_registration
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


def run_legacy_flow(revisions, catalog, inventory, reports):
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
    return prepared, expected, outlet


def run_reuse_family(revisions, catalog, inventory):
    """Freeze R0-R3, issue every piece and register the originals at the center."""
    configurations = (
        {'other_crossings': 1}, {}, {'new_inlet': True}, {'other_crossings': 2},
    )
    family = []
    for args in configurations:
        data = seam_registration(**args)
        revision = freeze(revisions, data)
        issued = {piece: issue(revisions, catalog, revision, piece) for piece in PIECES}
        ids = {piece: receive(inventory, fixed.raw) for piece, fixed in issued.items()}
        family.append((revision, issued, ids, args))
    return family


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

        prepared, expected, outlet = run_legacy_flow(revisions, catalog, inventory, reports)

        # R0-R3: the night shift only corrected one crossing on other pieces, but
        # the port leading out of piece A renumbered from p2 to p3/p4.
        family = run_reuse_family(revisions, catalog, inventory)
        r0, r1, r2, r3 = family
        for revision, _, _, args in family:
            observed = online(revisions, revision, 'S').as_record()
            if observed != {'kind': 'outlet', 'outlet': 'O2', 'hops': 1}:
                raise AssertionError(f'online reference changed for {args}: {observed}')

        # The station issues reuse declarations while the source is still online.
        decl_a_for_r2 = compatibility_for(revisions, catalog, r1[1]['A'].issue_id, r2[0])
        decl_a_for_r3 = compatibility_for(revisions, catalog, r1[1]['A'].issue_id, r3[0])
        decl_b_for_r3 = compatibility_for(revisions, catalog, r0[1]['B'].issue_id, r3[0])

        # The same R1 piece A independently serves two target revisions.
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

        # Offline reuse: target R2 with R1's piece A and R2's remaining pieces.
        r2_ids = [r1[2]['A']] + [r2[2][piece] for piece in ('0', '1', 'B')]
        reuse_r2 = review_reuse(
            inventory, reports, 'Qingqu', r2[0], r2_ids, [decl_a_for_r2], 'S'
        )
        r2_doc = json.loads(reuse_r2.report)
        print(f"复用 R1 的 A 签报 R2：{r2_doc['outcome']}，实际出处 {r2_doc['sources']}，"
              f"声明摘要 {r2_doc['reuse_declarations']}")

        # Target R3: the same R1 A receipt plus R0's B and R3's own pieces 0 and 1.
        r3_ids = [r1[2]['A'], r0[2]['B'], r3[2]['0'], r3[2]['1']]
        reuse_r3 = review_reuse(
            inventory, reports, 'Qingqu', r3[0], r3_ids,
            [decl_b_for_r3, decl_a_for_r3], 'S'
        )
        r3_doc = json.loads(reuse_r3.report)
        print(f"复用 R1 的 A 与 R0 的 B 签报 R3：{r3_doc['outcome']}，实际出处 {r3_doc['sources']}，"
              f"声明摘要 {r3_doc['reuse_declarations']}")
        if r2_doc['sources']['A'] != r3_doc['sources']['A']:
            raise AssertionError('the same original receipt must back both target revisions')
        if digest_declaration(decl_a_for_r2) == digest_declaration(decl_a_for_r3):
            raise AssertionError('declarations for different targets must stay distinct')

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
        for bundle in (reuse_r2, reuse_r3):
            if read(reopened, bundle.report_id) != bundle:
                raise AssertionError('reuse report cannot be re-fetched after reopening')
        print('重开中心后，原报告与两份复用报告均按号复领，首执保留实收出处与声明摘要。')

        _scenario('v9', {'start': 'S', 'samples': list(prepared), 'coverage': ['A', 'B']},
                  expected, actual, stored,
                  ['survey/reference.py', 'issue/evidence.py', 'review/trace.py', 'reports/history.py'],
                  '逐跳手算，提前版在第 1 和第 4 跳重访，对照版在第 2 和第 5 跳重访')
        _scenario('v5.seam_hops', {'start': 'T', 'sample': 'early.json', 'coverage': ['A', 'B']},
                  outlet, _outcome(drainage), _outcome(stored_drainage),
                  ['issue/segments.py', 'review/ports.py', 'review/trace.py', 'reports/history.py'],
                  '从 T 到接近格、乙幅格、回幅格、排口，各移动一跳')
        reuse_outcome = {'kind': 'outlet', 'outlet': 'O2', 'hops': 1}
        _scenario(
            'reuse.offline_seam',
            {'targets': [r2[0], r3[0]], 'reused_pieces': {'A': r1[1]['A'].issue_id,
                                                           'B': r0[1]['B'].issue_id}},
            reuse_outcome, _outcome(reuse_r3),
            _outcome(read(ReportStore(center), reuse_r3.report_id)),
            ['issue/compatibility.py', 'issue/declaration.py', 'review/reuse.py', 'reports/history.py'],
            '口号重编号但真实入幅口、跳数、排口与汇合关系等价，停源后按声明接通接缝',
        )


if __name__ == '__main__':
    main()
