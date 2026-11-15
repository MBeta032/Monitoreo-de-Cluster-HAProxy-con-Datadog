import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ART = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ART))
spec = importlib.util.spec_from_file_location('cierre', ART / 'cierre_hoy.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class Tests(unittest.TestCase):
    def test_plans(self):
        for rate in (10, 20, 40, 60):
            for duration in (300, 600, 900):
                for pattern in ('constante', 'gradual', 'escalonado', 'pico'):
                    phases = c.phases(pattern, rate, 2, duration)
                    self.assertEqual(sum(p['duration'] for p in phases), duration)
                    self.assertTrue(all(p['duration'] > 0 for p in phases))
                    self.assertEqual(max(max(p['arrivalRate'], p.get('rampTo', 0)) for p in phases), rate)
        jobs = c.plan(2)
        self.assertEqual(len(jobs), 14)
        self.assertEqual(sum(j['seconds'] for j in jobs), 85 * 60)
        self.assertEqual(sum(j['label'].startswith('roundrobin-') for j in jobs), 3)
        self.assertEqual(sum(j['label'].startswith('leastconn-') for j in jobs), 3)

    def fixture(self, root):
        art = root / 'artillery';art.mkdir()
        for name in ('normal.yml', 'pico.yml', 'taquilla.js'):
            (art / name).write_bytes((ART / name).read_bytes())
        cfg = root / 'haproxy.cfg';cfg.write_bytes(b'backend be_app\n    balance roundrobin\n')
        return art, cfg

    def test_run_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);art,cfg = self.fixture(root);folder = art / 'campanas/camp';folder.mkdir(parents=True)
            original = folder / 'conservado.json';original.write_text('original')
            commands = []
            class Fake:
                def __init__(self, command, **kwargs):
                    commands.append(command)
                    output = art / 'resultados' / command[-1].removeprefix('/results/')
                    output.parent.mkdir(parents=True,exist_ok=True)
                    output.write_text(json.dumps({'aggregate': {'counters': {'http.requests': 5, 'jj.flujo_ok': 1}}}))
                    self.stdout = io.StringIO('Salida simulada\n')
                def wait(self, **kwargs): return 0
                def poll(self): return 0
            job = {'label':'humo','grupos':['humo'],'pattern':'constante','rate':1,'seconds':1,'algorithm':'roundrobin'}
            with patch.multiple(c, ROOT=root, ART=art, CFG=cfg), patch.object(c,'effective_config',return_value=cfg.read_bytes()), \
                 patch.object(c,'fingerprint',return_value={'test':'hash'}), patch.object(c,'capture',return_value=SimpleNamespace(stdout='imagen')), \
                 patch.object(c.subprocess,'Popen',Fake), patch.object(c,'environment',return_value={'JJ_PASSWORD':'secreto-test'}):
                first,_ = c.run_one(folder,job,'reserva',True)
                second,_ = c.run_one(folder,job,'consulta',True)
            self.assertNotEqual(first['id'],second['id'])
            self.assertEqual(original.read_text(),'original')
            self.assertNotIn('secreto-test',json.dumps(commands))
            data = c.read(folder / first['id'] / 'escenario.json')
            self.assertEqual(len(data['scenarios'][0]['flow']),5)
            self.assertIn('X-CSRF-Token',data['scenarios'][0]['flow'][-2]['post']['headers'])
            self.assertEqual(data['config']['phases'][0]['arrivalCount'],1)
            for p in folder.rglob('*'):
                if p.is_file(): self.assertNotIn('secreto-test',p.read_text(encoding='utf-8'))

    def test_restore_after_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);art,cfg=self.fixture(root);original=cfg.read_bytes()
            humo=art/'campanas/humo/manifest.json'
            c.write(humo,{'estado':'completada','huellas':{'x':'y'},'corridas':[{'operacion':'reserva'}]})
            c.write(art/'campanas/ultimo_humo.json',{'manifest':humo.relative_to(root).as_posix()})
            def switch(*args): cfg.write_bytes(b'backend be_app\n    balance leastconn\n')
            with patch.multiple(c,ROOT=root,ART=art,CFG=cfg), patch.object(c,'preflight'), \
                 patch.object(c,'fingerprint',return_value={'x':'y'}),patch.object(c,'set_algorithm',side_effect=switch), \
                 patch.object(c,'ready'),patch.object(c,'capture'),patch.object(c,'report'), \
                 patch.object(c,'run_one',side_effect=RuntimeError('fallo simulado')):
                with self.assertRaises(RuntimeError): c.campaign(2,None)
            self.assertEqual(cfg.read_bytes(),original)
            manifest=c.read(next((art/'campanas').glob('taquilla-*/manifest.json')))
            self.assertEqual(manifest['estado'],'interrumpida')
            self.assertEqual(manifest['restauracion_haproxy'],'aplicada')

    def test_auth_failures(self):
        for status in (401,403):
            with self.assertRaises(RuntimeError): c.check_auth({'http.codes.'+str(status):1})
        c.check_auth({'http.codes.500':10})  # Se registra como dato de carga, no error de autenticación.


if __name__ == '__main__':
    unittest.main()
