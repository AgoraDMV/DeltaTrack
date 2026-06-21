# Bill Index
Aka the *Big Beautiful Index*

This module is a cache for bill metadata, intended to accumulate information about large volumes of bills.

The guiding idea behind the cache is that each bill has an identifying slug of the form:

{congress}-{type}-{number}

e.g. `119-hr-1` for the 1st House Resolution bill of the 119th Congress.

Aside from a uniquely identifying slug, each bill can have arbitrary metadata. Adding a bill to the index will automatically update metadata if a bill with the same ID exists already, otherwise create a new record. The bill index can be used to prevent duplicate downloads when managing large volumes of bill data or to combine metadata from different sources.