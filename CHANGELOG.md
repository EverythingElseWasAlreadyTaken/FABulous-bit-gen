# Changelog

## [0.3.1](https://github.com/FPGA-Research/FABulous-bit-gen/compare/v0.3.0...v0.3.1) (2026-07-03)


### Bug Fixes

* **ci:** stop tagging rolling v0/v0.3 refs on release ([fd87ced](https://github.com/FPGA-Research/FABulous-bit-gen/commit/fd87ceded715f48cced6c31dddc3f469aab8cc2a))
* **ci:** stop tagging rolling v0/v0.3 refs on release ([ca8f406](https://github.com/FPGA-Research/FABulous-bit-gen/commit/ca8f4066dc7c030b23023140dfd1cf0b7e5c2ee9))

## [0.3.0](https://github.com/FPGA-Research/FABulous-bit-gen/compare/v0.2.0...v0.3.0) (2026-05-12)


### Features

* add comprehensive pytest test suite with 129 tests ([b49796f](https://github.com/FPGA-Research/FABulous-bit-gen/commit/b49796f9b1aea8c892e8cf2273c855ec7b679149))
* add legacy flag to include/exclude border rows in bitstream ([22f66ed](https://github.com/FPGA-Research/FABulous-bit-gen/commit/22f66ed71f066ff431044843a48901978bf05b39))
* backwards-compat -genBitstream flag + improved help text ([01b5fd3](https://github.com/FPGA-Research/FABulous-bit-gen/commit/01b5fd349ccbf5300a42460b7b326a615555ae31))
* extend overwrite detection to unmasked bitstream (TileSpecs_No_Mask) ([5fd5c79](https://github.com/FPGA-Research/FABulous-bit-gen/commit/5fd5c799e4bb1dbacaeb9d3b98faee86d4345222))
* read FABulousVersion from spec dict with default 1.0 ([191300a](https://github.com/FPGA-Research/FABulous-bit-gen/commit/191300a211c2c4637233bd8afaf586a4a828f8e9))
* remap I0mux -> IOmux for old FABulous spec versions ([232bf87](https://github.com/FPGA-Research/FABulous-bit-gen/commit/232bf874a8bb2a32f8ed79bcbea10833da50faaf))
* warn when a FASM feature overwrites an already-set tile bit ([a730033](https://github.com/FPGA-Research/FABulous-bit-gen/commit/a730033e5d4a032c71e627c7c2c1ab74fb4757cd))


### Bug Fixes

* correct test suite issues and fix two bugs in bit_gen.py ([ec0e900](https://github.com/FPGA-Research/FABulous-bit-gen/commit/ec0e900e6d9d71fc827e10daf23e9ccbba60e4be))
* harden bit_gen.py against several latent bugs ([60a7981](https://github.com/FPGA-Research/FABulous-bit-gen/commit/60a79817e002cd5943181c62b778205687652172))
* harden bit_gen.py against silent failures and stale internals ([b7139d7](https://github.com/FPGA-Research/FABulous-bit-gen/commit/b7139d723c356ac9b5006fc934041f22adaa624e))
* pre-commit violations (ruff E741, pydoclint DOC101/DOC501) ([69428c4](https://github.com/FPGA-Research/FABulous-bit-gen/commit/69428c434b0eb30d1a096b463504c84b92f0f05d))
* raise SpecMissMatch when TileSpecs absent but TileMap is present ([337f680](https://github.com/FPGA-Research/FABulous-bit-gen/commit/337f680123e3e8379a40217169df6e988b162845))
* resolve all ruff violations in test suite ([ca03768](https://github.com/FPGA-Research/FABulous-bit-gen/commit/ca037683f371084817fe1a8e9b293b820cc50958))
* **tests:** replace zip(strict=False) with direct list equality in integration tests ([5eb2e08](https://github.com/FPGA-Research/FABulous-bit-gen/commit/5eb2e08eec6bd660878e043684c8b95fbc48afe6))
* track touched bits explicitly to catch zero-valued overwrites ([9663c26](https://github.com/FPGA-Research/FABulous-bit-gen/commit/9663c2644456160c226e45cc6bbb5af5da56d716))


### Documentation

* add tests/README.md explaining layout, fixtures, and integration tests ([be8c499](https://github.com/FPGA-Research/FABulous-bit-gen/commit/be8c49930de234f31b2214067411595ae275083e))
* extend docstrings with parameters, returns, and raises sections ([e27487a](https://github.com/FPGA-Research/FABulous-bit-gen/commit/e27487abcee7c41329cb98ddc19832523899d803))
