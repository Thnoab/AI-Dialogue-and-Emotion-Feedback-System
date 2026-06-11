
document.querySelectorAll('textarea').forEach(textarea => {
    textarea.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
});


document.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', function(e) {

    });
});