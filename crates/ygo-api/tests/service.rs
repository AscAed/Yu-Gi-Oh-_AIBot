use ygo_api::ApiService;

#[test]
fn exposes_the_ocg_mr5_contract_version() {
    assert_eq!(ApiService::new().ruleset(), "ocg-mr5");
}
