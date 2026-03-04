window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, context) {
            var dept = feature.properties.dept || feature.properties.NAME;
            var cm = context.hideout.colorMap || {};
            return {
                fillColor: cm[dept] || '#3A3D42',
                color: '#5C5C5C',
                weight: 1.5,
                fillOpacity: 0.45,
            };
        },
        function1: function(feature) {
            return {
                fillColor: '#00BCD4',
                color: '#00ACC1',
                weight: 2,
                fillOpacity: 0.18,
                dashArray: '6 4'
            };
        },
        function2: function(feature) {
            return {
                fillColor: '#FF5722',
                color: '#E64A19',
                weight: 2,
                fillOpacity: 0.18,
                dashArray: '6 4'
            };
        },
        function3: function(feature) {
            return {
                fillColor: '#FFEB3B',
                color: '#FBC02D',
                weight: 2,
                fillOpacity: 0.22,
                dashArray: '4 3'
            };
        },
        function4: function(feature) {
            return {
                fillColor: '#9C27B0',
                color: '#7B1FA2',
                weight: 1.5,
                fillOpacity: 0.10,
                dashArray: '5 3'
            };
        },
        function5: function(feature, layer) {
            var z = feature.properties.ZCTA5 || '';
            if (z) {
                layer.bindTooltip(z, {
                    permanent: true,
                    direction: 'center',
                    className: 'zcta-label',
                    offset: [0, 0]
                });
            }
        },
        function6: function(feature, context) {
            var z = feature.properties.ZCTA5 || '';
            var cm = (context.hideout || {}).zipColorMap || {};
            var c = cm[z];
            if (c) {
                return {
                    fillColor: c,
                    color: 'rgba(123,31,162,0.5)',
                    weight: 1,
                    fillOpacity: 0.30,
                    dashArray: ''
                };
            }
            return {
                fillColor: 'transparent',
                color: 'rgba(123,31,162,0.25)',
                weight: 0.5,
                fillOpacity: 0,
                dashArray: '4 3'
            };
        },
        function7: function(feature, layer) {
            var p = feature.properties;
            var z = p.ZCTA5 || '';
            var calls = p._calls || 0;
            if (calls > 0) {
                var tip = '<b>' + z + '</b> &mdash; ' + calls + ' calls, ' + p._rt + ' min RT';
                layer.bindTooltip(tip, {
                    sticky: true,
                    direction: 'top',
                    opacity: 0.92
                });
            }
        }
    }
});