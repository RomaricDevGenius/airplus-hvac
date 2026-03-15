/**
 * Script Electro pour le site client : carrousels produits, panier, zoom, etc.
 */
(function($) {
	"use strict";

	$('.menu-toggle > a').on('click', function (e) {
		e.preventDefault();
		$('#responsive-nav').toggleClass('active');
	});

	$('.cart-dropdown').on('click', function (e) {
		e.stopPropagation();
	});

	// Carrousel "New Products" / "Top selling"
	$('.products-slick').each(function() {
		var $this = $(this),
			$nav = $this.attr('data-nav');
		$this.slick({
			slidesToShow: 4,
			slidesToScroll: 1,
			autoplay: true,
			infinite: true,
			speed: 300,
			dots: false,
			arrows: true,
			appendArrows: $nav ? $nav : false,
			responsive: [{
				breakpoint: 991,
				settings: { slidesToShow: 2, slidesToScroll: 1 }
			}, {
				breakpoint: 480,
				settings: { slidesToShow: 1, slidesToScroll: 1 }
			}]
		});
	});

	$('.products-widget-slick').each(function() {
		var $this = $(this),
			$nav = $this.attr('data-nav');
		$this.slick({
			infinite: true,
			autoplay: true,
			speed: 300,
			dots: false,
			arrows: true,
			appendArrows: $nav ? $nav : false,
		});
	});

	if (document.getElementById('product-main-img')) {
		$('#product-main-img').slick({
			infinite: true,
			speed: 300,
			dots: false,
			arrows: true,
			fade: true,
			asNavFor: '#product-imgs',
		});
	}
	if (document.getElementById('product-imgs')) {
		$('#product-imgs').slick({
			slidesToShow: 3,
			slidesToScroll: 1,
			arrows: true,
			centerMode: true,
			focusOnSelect: true,
			centerPadding: 0,
			vertical: true,
			asNavFor: '#product-main-img',
			responsive: [{
				breakpoint: 991,
				settings: { vertical: false, arrows: false, dots: true }
			}]
		});
	}

	var zoomMainProduct = document.getElementById('product-main-img');
	if (zoomMainProduct) {
		$('#product-main-img .product-preview').zoom();
	}

	$('.input-number').each(function() {
		var $this = $(this),
			$input = $this.find('input[type="number"]'),
			up = $this.find('.qty-up'),
			down = $this.find('.qty-down');
		down.on('click', function () {
			var value = parseInt($input.val(), 10) - 1;
			$input.val(value < 1 ? 1 : value).change();
		});
		up.on('click', function () {
			$input.val(parseInt($input.val(), 10) + 1).change();
		});
	});

	var priceSlider = document.getElementById('price-slider');
	if (priceSlider && typeof noUiSlider !== 'undefined') {
		noUiSlider.create(priceSlider, {
			start: [1, 999],
			connect: true,
			step: 1,
			range: { min: 1, max: 999 }
		});
	}
})(jQuery);
