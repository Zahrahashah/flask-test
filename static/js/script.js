  $(document).ready(function() {
    // Navbar Scroll Effect
    $(window).scroll(function () {
        var scroll = $(window).scrollTop();
        if (scroll >= 10) {
            $(".navbar").addClass("nav-scroll");
        } else {
            $(".navbar").removeClass("nav-scroll");
        }
    });

    // Smooth Quote Fade Animation
    let quoteIndex = 0;
    const quoteElements = document.querySelectorAll('.quote');

    function showNextQuote() {
        quoteElements.forEach(q => q.classList.remove('active'));
        quoteElements[quoteIndex].classList.add('active');
        quoteIndex = (quoteIndex + 1) % quoteElements.length;
    }

    if (quoteElements.length > 0) {
        showNextQuote();
        setInterval(showNextQuote, 4000);
    }

    // Testimonial Slider
    $('.testimonial_slider').slick({
        dots: true,
        infinite: true,
        speed: 300,
        slidesToShow: 2,
        slidesToScroll: 1,
        responsive: [
            {
                breakpoint: 1024,
                settings: {
                    slidesToShow: 2,
                    slidesToScroll: 1,
                    infinite: true,
                    dots: true
                }
            },
            {
                breakpoint: 768,
                settings: {
                    slidesToShow: 1,
                    slidesToScroll: 1
                }
            }
        ]
    });

    // Course Criteria Calculator Logic
    $('#criteriaCalculator').on('submit', function (e) {
        e.preventDefault();
        var age = $('#age').val();
        var disability = $('#disability').val();
        var learning = $('#learning').val();

        var recommendation = "Based on your input, we recommend: ";

        if (age <= 5) {
            recommendation += "Early Intervention Programs with a focus on ";
        } else if (age <= 12) {
            recommendation += "Foundational Skills Courses with a focus on ";
        } else {
            recommendation += "Advanced Life Skills and Vocational Training with a focus on ";
        }

        if (disability === 'autism') {
            recommendation += "Sensory Learning and Communication Skills.";
        } else if (disability === 'hearing') {
            recommendation += "Sign Language and Auditory Training.";
        } else if (disability === 'visual') {
            recommendation += "Braille and Tactile Learning.";
        } else if (disability === 'physical') {
            recommendation += "Adaptive Physical Activities.";
        } else {
            recommendation += "Cognitive and Social Skills Development.";
        }

        recommendation += " The " + learning + " learning approach will be integrated.";

        $('#calculatorResult').html('<p>' + recommendation + '</p>').addClass('animate__animated animate__fadeIn');
    });
});
