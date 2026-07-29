#!/usr/bin/env python3
from efficiency_policy import recommend
assert recommend(20,2_000_000,1000,'low',True,[])['token_policy']=='batch'
assert recommend(20,2_000_000,1000,'high',True,[])['token_policy']=='external_review'
assert recommend(20,2_000_000,1000,'low',False,[])['token_policy']=='direct'
assert recommend(1,100,100,'low',True,[{'status':'failed'}]*3)['guardrail_triggered']
print('efficiency-policy tests passed')
