<script>
function select_version(container_id, choice) {
    var container = document.getElementById(container_id);
    var choices = container.getElementsByClassName('choice');
    for (let i=0; i<choices.length; i++) {
        if (choices[i].getAttribute('name') === choice) {
            choices[i].style.display = 'block';
        } else {
            choices[i].style.display = 'none';
        }
    }
    buttons = container.getElementsByTagName('button');
    for (let i=0; i<buttons.length; i++) {
        if (buttons[i].getAttribute('name') === choice) {
            buttons[i].className = 'active';
        } else {
            buttons[i].className = 'inactive';
        }
    }
}

function startup() {
    select_version('one_page_app_switcher', 'Find');
}
</script>
