import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path

def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).parents[1]/'scripts'/f'{name}.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

b=module('benchmark')
c=module('capture_probe')

class FeasibilityTests(unittest.TestCase):
    def test_quantiles_include_tail(self):
        self.assertEqual(b.summary(range(1,21)),{'count':20,'median':10.5,'p95':19,'max':20})
    def test_empty_measurements_are_not_zero_latency(self):
        self.assertIsNone(b.summary([])['median'])
    def test_missing_gpu_blocks_inference(self):
        from argparse import Namespace
        with patch.object(b,'inventory',return_value={'gpu':{'error':'FileNotFoundError'}}):
            self.assertEqual(b.run(Namespace(output='unused'))['status'],'blocked_no_nvidia_smi')
    def test_non_windows_cannot_pass_capture(self):
        from argparse import Namespace
        with patch.object(c.os,'name','posix'):
            self.assertEqual(c.probe(Namespace(mode='window'))['status'],'blocked_requires_windows')
    def test_inference_destination_is_fixed_loopback(self):
        with patch.object(b.urllib.request,'build_opener') as factory:
            b.api('generate',{'model':'candidate'})
            request=factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'http://127.0.0.1:11434/api/generate')
            self.assertEqual(factory.call_args.args[0].proxies,{})

if __name__=='__main__': unittest.main()
