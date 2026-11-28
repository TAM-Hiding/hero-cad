import json
import pytest
from hero_cad.palette import BASE_COLORS, COLORS, decode_palette, encode_palette
from hero_cad.snap_appearance import DEFAULTS, validated_options
from hero_cad.ui.snap_indicators import symbol_paths, dashed_guide


@pytest.mark.parametrize('target,cells,points', [
    ('MODEL ENDPOINT',1,5), ('MODEL MIDPOINT',1,4), ('MODEL EDGE',1,5),
    ('MODEL CENTER',3,37), ('CENTER',3,37), ('ENDPOINT',1,5), ('ORIGIN',2,4), ('GRID',2,4),
])
def test_supported_symbols_are_vector_strokes(target,cells,points):
    paths = symbol_paths(target,'Triangle')
    assert len(paths) == cells
    assert sum(len(p) for p in paths) == points
    assert all(-1 <= x <= 1 and -1 <= y <= 1 for path in paths for x,y in path)


def test_centerline_symbol_and_dash_styles():
    triangle = symbol_paths('MODEL MIDPOINT','Triangle')
    centerline = symbol_paths('MODEL MIDPOINT','Centerline (C/L)')
    assert len(centerline) == 2 and centerline != triangle
    paths = [dashed_guide((4,8),(0,1),84,1,style) for style in ('Dashed','Dash-dot','Dotted')]
    assert len({len(path) for path in paths}) == 3
    assert all(x == 4 for path in paths for segment in path for x,y in segment)
    assert all(-34 <= y <= 50 for path in paths for segment in path for x,y in segment)


@pytest.mark.parametrize('value',[{'size':True},{'size':0},{'size':41},{'size':10**1000},{'weight':float('inf')},
                                {'weight':.1},{'midpoint':'Intersection'},{'unknown':True},[]])
def test_invalid_portable_options_are_rejected(value):
    with pytest.raises(ValueError):
        validated_options(value)


def test_palette_optional_settings_roundtrip_and_legacy_colors():
    colors = {key: spec.default or '#123456' for key,spec in COLORS.items()}
    text = encode_palette(colors, {}, snap_indicators={**DEFAULTS,'midpoint':'Centerline (C/L)','color':'Red'})
    _, _, options = decode_palette(text,include_snap=True)
    assert options['color'] == 'Red' and options['midpoint'] == 'Centerline (C/L)'
    legacy = json.dumps({'format':'hero-ui-palette','version':1,
                         'colors':{key:colors[key] for key in BASE_COLORS}})
    _, _, options = decode_palette(legacy,include_snap=True)
    assert options == {}
    broken = json.loads(text)
    broken['snap_indicators']['size'] = -1
    with pytest.raises(ValueError):
        decode_palette(json.dumps(broken))
