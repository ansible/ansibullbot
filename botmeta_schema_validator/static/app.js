(function() {

    ngApp = angular.module('ngApp', ['blockUI', 'ui.bootstrap']);

    ngApp.controller('mainController', [
        '$scope',
        '$http',
        '$sce',
        function($scope, $http, $sce) {
            //$scope.variables = '';
            $scope.filepaths = '';
            //$scope.template = '';
            $scope.current_meta = '';
            $scope.rendered = '';
            $scope.error = '';

            //$scope.templateExample = '{{ foo }}';

            $scope.current = function() {

                //console.log('inside current scope!');
                $http.get(
                    'current'
                ).then(
                    function(response) {
                        //console.log('here is the current data ...');
                        //console.log(response);
                        //console.log(response.data);
                        $scope.current_meta = response.data;
                    }
                )
            }

            $scope.render = function(tag) {
                var tag = tag || 'latest';
                $scope.rendered = '';
                $scope.error = '';
                $http.post(
                    'render',
                    {
                        filepaths: $scope.filepaths,
                        current_meta: $scope.current_meta,
                        tag: tag,
                    }
                ).then(
                    function(response) {
                        //$scope.rendered = response.data;
                        $scope.rendered = JSON.stringify(response.data, null, "  ");
                    },
                    function(response) {
                        console.log(response);
                        $scope.error = response.data.error;
                    }
                )
            }
        }
    ]);
})();

