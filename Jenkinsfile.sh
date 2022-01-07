set -e
echo "----------------------------------------------"
echo "$JOB_NAME build $BUILD_NUMBER"
WORKSPACE_ROOT="$WORKSPACE/$BUILD_NUMBER"
echo "Setting up build in $WORKSPACE_ROOT"
TEST_OUTPUT_DIR_REL=testcase_output
TEST_OUTPUT_DIR="$WORKSPACE_ROOT/$TEST_OUTPUT_DIR_REL"
TEST_DATA_DIR="$WORKSPACE/../../../test-data"
PROJECTS_DIR_REL="projects"
PROJECTS_DIR=$WORKSPACE_ROOT/$PROJECTS_DIR_REL
mkdir $TEST_OUTPUT_DIR
echo "----------------------------------------------"
echo "\nEnvironment:"
df -h .
echo "----------------------------------------------"
cat /proc/meminfo
echo "----------------------------------------------"

#build using docker file in directory:
cd $PROJECTS_DIR/meqtrees-pyxis
IMAGENAME="mtpyxispr"

# build and test
BUILDTAG=${IMAGENAME}36:$BUILD_NUMBER
docker build -f .ci/py3.6.ubuntu18.04.docker  -t "${BUILDTAG}" --no-cache=true .
#BUILDTAG=${IMAGENAME}38:$BUILD_NUMBER
#docker build -f .ci/py3.8.ubuntu20.04.docker  -t "${BUILDTAG}" --no-cache=true .
