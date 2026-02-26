from pymodaq.extensions.data_mixer.model import get_models



def test_get_models():
    models = get_models()
    pass
    assert len(models) >= 3
    class_names = [model['class'].__name__ for model in models]
    assert 'DataMixerGaussianFitModel' in class_names
    assert 'DataMixerModelEquation' in class_names
    assert 'DataMixerModelH5' in class_names