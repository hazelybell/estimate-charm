LIB_DIR=../../lib

default: lp-clustered.svg

# Generate import dependency graph
lp.sfood:
	sfood -i -u -I $(LIB_DIR)/sqlobject -I $(LIB_DIR)/schoolbell \
	-I $(LIB_DIR)/devscripts -I $(LIB_DIR)/contrib \
	-I $(LIB_DIR)/canonical/not-used $(LIB_DIR)/canonical \
	$(LIB_DIR)/lp 2>/dev/null | grep -v contrib/ \
	| grep -v sqlobject | grep -v BeautifulSoup | grep -v psycopg \
	| grep -v schoolbell | grep -v '/tests/' | grep -v '/ftests/' \
    | grep -v 'lp/services/config' > lp.sfood.tmp
	mv lp.sfood.tmp lp.sfood


# Cluster the import dependency graph
lp-clustered.sfood: lp.sfood lp-sfood-packages
	sfood-cluster -f lp-sfood-packages < lp.sfood > lp-clustered.sfood.tmp
	mv lp-clustered.sfood.tmp lp-clustered.sfood


# Build the visual graph
lp-clustered.dot: lp-clustered.sfood
	sfood-graph -p < lp-clustered.sfood > lp-clustered.dot.tmp
	mv lp-clustered.dot.tmp lp-clustered.dot


# Render to svg
lp-clustered.svg: lp-clustered.dot
	dot -Tsvg < lp-clustered.dot > lp-clustered.svg.tmp
	mv lp-clustered.svg.tmp lp-clustered.svg

clean:
	$(RM) -f lp.sfood lp-clustered.sfood lp-clustered.dot lp-clustered.svg


.PHONY: clean
